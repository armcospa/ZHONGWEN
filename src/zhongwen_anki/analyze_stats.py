"""Turn the CSV from export_stats into a comprehensive HTML learning report.

Reads the CSV exported by zhongwen_anki.export_stats (and optionally the
card-snapshot CSV) and generates a self-contained HTML report with:

  - Overview KPIs (reviews, words, accuracy, time, streaks)
  - Accuracy breakdown by card type and HSK level
  - Daily review volume and accuracy trend (7-day moving average)
  - Retention by interval bucket
  - Accuracy by day of week and time of day
  - **Deep failure analysis** — hardest words, lapse patterns, mastery curves
  - **Linguistic analysis** — difficulty by tone pattern, character complexity
  - **Response time analysis** — speed by skill
  - **Study recommendations** — personalized actionable suggestions

Usage:
    zhongwen-anki-analyze-stats
    zhongwen-anki-analyze-stats -i docs/local/estadisticas/anki_reviews.csv \
                                 -o docs/local/estadisticas/report.html \
                                 --cards docs/local/estadisticas/anki_reviews.cards.csv

Everything is derived from the CSV with pandas; no network access required.
Charts are rendered with matplotlib and embedded as base64-encoded PNG images
directly in the HTML, so the report is fully self-contained.
"""
import argparse
import base64
import html as html_module
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from zhongwen_anki.utilities import pinyin_to_numbered


# --- palette ------------------------------------------------------------
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514d"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"
RED = "#c0392b"
ORANGE = "#e67e22"
GREEN = "#27ae60"
YELLOW = "#f1c40f"
PURPLE = "#8e44ad"
TEAL = "#16a085"

CARD_TYPE_DESCRIPTIONS = {
    "H2M": "hanzi → significado",
    "M2H": "significado → dibujar hanzi",
    "H2P": "hanzi → escribir pinyin",
    "PM2H": "pinyin + significado → dibujar hanzi",
    "P2M": "pinyin → significado",
    "M2P": "significado → escribir pinyin",
    "P2H": "pinyin → dibujar hanzi",
    "HM2P": "hanzi + significado → escribir pinyin",
    "HP2M": "hanzi + pinyin → significado",
    "Toda la información": "consulta",
}

LEGACY_CARD_TYPES = {
    "Hanzi -> Significado": "H2M",
    "Significado -> Hanzi": "M2H",
    "Escribir Pinyin": "H2P",
    "Escribir Hanzi": "PM2H",
    "Pinyin -> Significado": "P2M",
    "Significado -> Pinyin": "M2P",
}

# Card type that is informational only — exclude from accuracy analysis.
INFO_ONLY_CARD_TYPE = "Toda la información"

SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]
ACCURACY_COLORS = {
    "excellent": GREEN,  # >= 90%
    "good": BLUE,        # 75-89%
    "fair": ORANGE,      # 60-74%
    "poor": RED,         # < 60%
}

WEEKDAY_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
WEEKDAY_ORDER = list(WEEKDAY_ES.values())

LEVEL_RE = re.compile(r"HSK(\d+)")

# Regex to extract tone numbers from numbered pinyin (e.g. "ai4hao4" → [4, 4])
_NUMBERED_TONE_RE = re.compile(r"([1-5])")

# --- thresholds -----------------------------------------------------------
LOW_ACCURACY = 0.6
CRITICAL_ACCURACY = 0.5
WEAK_SKILL_ACCURACY = 0.7
EXCELLENT_ACCURACY = 0.9
LOW_EASE_ATTENTION = 200
EASE_HELL = 150
MIN_ACTIVE_DAYS_FOR_RECS = 7
MIN_REVIEWS_FOR_RECS = 200
# Minimum number of reviews a word/group needs before we report it. Below this
# the figures are just noise (e.g. a tone pattern seen once at 100%).
MIN_GROUP_REVIEWS = 5

# Card types that ask the user to write or recognize pinyin (for tone analysis)
PINYIN_OUTPUT_CARD_TYPES = {"H2P", "M2P", "HM2P"}

# Card types where the hanzi is the target (for character difficulty)
HANZI_TARGET_CARD_TYPES = {"M2H", "PM2H", "P2H"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Segoe UI", "Arial", "DejaVu Sans"],
    "text.color": INK_PRIMARY,
    "axes.labelcolor": INK_SECONDARY,
    "axes.edgecolor": GRID,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.size": 10,
})


# --- loading ------------------------------------------------------------

def load(csv_path: Path, cards_csv: Optional[Path] = None) -> tuple:
    """Load reviews CSV and optional card snapshot.

    Returns (reviews_df, cards_df_or_None).
    """
    df = pd.read_csv(csv_path, parse_dates=["review_datetime"])
    if "card_type" not in df.columns:
        df["card_type"] = "Desconocido"
    df["card_type"] = df["card_type"].fillna("Desconocido").replace(LEGACY_CARD_TYPES)
    df["level"] = df["deck"].fillna("").map(_level_from_deck)

    # Ensure 'word' column exists for tables (fallback to note_id for old CSVs)
    if "word" not in df.columns:
        df["word"] = df["note_id"].astype(str)

    # If vocab-enriched columns exist, keep them; otherwise derive level from deck
    if "vocab_level" in df.columns and df["vocab_level"].notna().any():
        df["level"] = df["vocab_level"].where(
            df["vocab_level"].notna() & (df["vocab_level"] != ""), df["level"]
        )

    cards = None
    if cards_csv is not None and cards_csv.exists():
        cards = pd.read_csv(cards_csv, dtype=str)
        # Convert numeric columns for proper joins
        for col in ["card_id", "note_id", "queue", "type", "ease_factor_percent", "lapses"]:
            if col in cards.columns:
                cards[col] = pd.to_numeric(cards[col], errors="coerce")
        # FSRS columns should also be numeric
        for col in ["fsrs_stability", "fsrs_difficulty"]:
            if col in cards.columns:
                cards[col] = pd.to_numeric(cards[col], errors="coerce")

    return df, cards


def _ensure_note_id(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure df has note_id column for grouping.

    If note_id is missing (old CSV), derive it from word column.
    If both missing, create a synthetic one.
    Returns df (may be a copy if columns were added).
    """
    if df.empty:
        return df
    if "note_id" not in df.columns:
        df = df.copy()
        if "word" in df.columns:
            df["note_id"] = df["word"]
        else:
            df["note_id"] = range(len(df))
    return df


def filter_user_answers(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to only user answers, excluding system actions (reschedule, delete).

    Uses the `is_user_answer` column from the CSV (added by Phase 2 export_stats).
    For backward compatibility with old CSVs missing this column, applies fallback:
    ease >= 1 AND review_type NOT IN (4, 5) by numeric code OR
    review_type NOT IN ("manual", "rescheduled") by label.
    """
    if "is_user_answer" in df.columns:
        mask = df["is_user_answer"].astype(str).str.lower() == "true"
    else:
        # Fallback for old CSVs without is_user_answer column.
        # CSV saves review_type as LABEL ("manual", "review"), not number.
        # Also ease could be 0 for system actions.
        rev_type_col = df["review_type"] if "review_type" in df.columns else pd.Series("", index=df.index)
        rev_type_str = rev_type_col.astype(str).str.lower()
        mask = ~rev_type_str.isin(["manual", "rescheduled", "4", "5"])
        # Also exclude rows where ease == 0 (system actions)
        if "ease" in df.columns:
            ease = pd.to_numeric(df["ease"], errors="coerce").fillna(0)
            mask = mask & (ease >= 1)
    return df[mask].copy()


def exclude_info_only(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude informational-only card types from accuracy analysis."""
    if df.empty or "card_type" not in df.columns:
        return df
    return df[df["card_type"] != INFO_ONLY_CARD_TYPE]


def _level_from_deck(deck: str) -> str:
    m = LEVEL_RE.search(deck or "")
    return f"HSK{m.group(1)}" if m else "Sin nivel"


def _level_sort_key(level: str) -> int:
    m = LEVEL_RE.fullmatch(level)
    return int(m.group(1)) if m else 999


# --- metrics ------------------------------------------------------------

def overview(df: pd.DataFrame, today: Optional[date] = None) -> dict:
    if df.empty:
        return {"total_reviews": 0}
    span_days = (df["review_datetime"].max() - df["review_datetime"].min()).days + 1
    active_days = df["review_datetime"].dt.date.nunique()
    streaks = _calculate_streaks(df, today=today)
    # Use word column for unique_words when available (backward compat), else note_id
    unique_words = df["word"].nunique() if "word" in df.columns else df["note_id"].nunique()
    return {
        "total_reviews": len(df),
        "unique_words": unique_words,
        "unique_card_types": df["card_type"].nunique(),
        "date_start": df["review_datetime"].min(),
        "date_end": df["review_datetime"].max(),
        "span_days": span_days,
        "active_days": active_days,
        "total_time_hours": df["time_seconds"].sum() / 3600,
        "overall_accuracy": df["is_correct"].mean(),
        "avg_reviews_per_active_day": len(df) / active_days if active_days else 0,
        "avg_time_per_review": df["time_seconds"].mean(),
        "current_streak": streaks["current"],
        "longest_streak": streaks["longest"],
        "streak_alive": streaks["alive"],
        "last_streak_ended": streaks.get("last_ended"),
        "total_again": (df["ease_label"] == "Again").sum(),
        "total_hard": (df["ease_label"] == "Hard").sum(),
        "total_good": (df["ease_label"] == "Good").sum(),
        "total_easy": (df["ease_label"] == "Easy").sum(),
    }


def _calculate_streaks(df: pd.DataFrame, today: Optional[date] = None) -> dict:
    """Calculate current and longest study streaks (consecutive active days).

    Streak is 'alive' if the last active day is today or yesterday.
    If last active day is before yesterday, streak is broken.

    Args:
        df: Reviews dataframe with 'review_datetime' column.
        today: Reference date for streak calculation (default: actual today).
    """
    active_dates = sorted(set(df["review_datetime"].dt.date))
    if not active_dates:
        return {"current": 0, "longest": 0, "alive": False}

    reference = today or date.today()
    last_active = active_dates[-1]

    # Calculate longest streak
    longest = 1
    temp = 1
    for i in range(1, len(active_dates)):
        if active_dates[i] - active_dates[i - 1] == timedelta(days=1):
            temp += 1
            longest = max(longest, temp)
        else:
            temp = 1

    # Calculate current streak (going backwards from last active day)
    current = 1
    for i in range(len(active_dates) - 1, 0, -1):
        if active_dates[i] - active_dates[i - 1] == timedelta(days=1):
            current += 1
        else:
            break

    # Check if streak is alive
    days_since_last = (reference - last_active).days
    alive = days_since_last <= 1

    result: dict = {"current": current if alive else 0, "longest": longest, "alive": alive}

    if not alive:
        result["last_ended"] = last_active.strftime("%Y-%m-%d")

    return result


def accuracy_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    g = (
        df.groupby(column)
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"),
             avg_time_s=("time_seconds", "mean"),
             agains=("ease_label", lambda s: (s == "Again").sum()))
        .reset_index()
        .sort_values("accuracy")
    )
    return g


def daily_trend(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.set_index("review_datetime")
        .resample("D")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"),
             avg_time=("time_seconds", "mean"))
    )
    daily["accuracy_7d"] = daily["accuracy"].rolling(7, min_periods=1).mean()
    daily["reviews_7d"] = daily["reviews"].rolling(7, min_periods=1).mean()
    return daily.dropna(subset=["reviews"]).reset_index()


def retention_by_interval(df: pd.DataFrame) -> pd.DataFrame:
    """Retention by interval bucket with sample sizes and reliability markers.

    Buckets: 1d, 2-3d, 4-7d, 8-30d, >30d
    Shows sample size (n) for each bucket and marks unreliable buckets (n < 5).
    """
    reviewed = df[(df["review_type"] == "review") & (df["last_interval"] > 0)].copy()
    if reviewed.empty:
        return pd.DataFrame(columns=["bucket", "reviews", "accuracy", "reliable"])
    bins = [0, 1, 3, 7, 30, float("inf")]
    labels = ["1d", "2-3d", "4-7d", "8-30d", ">30d"]
    reviewed["bucket"] = pd.cut(reviewed["last_interval"], bins=bins, labels=labels)
    result = (
        reviewed.groupby("bucket", observed=True)
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )
    result["reliable"] = result["reviews"] >= 5
    return result


def accuracy_by_weekday(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy()
    tmp["weekday"] = tmp["review_datetime"].dt.day_name().map(WEEKDAY_ES)
    g = (
        tmp.groupby("weekday")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reindex(WEEKDAY_ORDER)
        .dropna(how="all")
        .reset_index()
    )
    return g


def accuracy_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy()
    tmp["hour"] = tmp["review_datetime"].dt.hour
    g = (
        tmp.groupby("hour")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )
    return g


# --- deep failure analysis -----------------------------------------------

def hardest_words(df: pd.DataFrame, min_reviews: int = 3, top: int = 25) -> pd.DataFrame:
    """Words with worst accuracy, ranked by (accuracy ASC, Fallos DESC).

    Groups by note_id (not word) since same hanzi can represent different words.
    Includes word column for display (first word value per group).
    """
    agg_dict = {
        "reviews": ("is_correct", "size"),
        "agains": ("ease_label", lambda s: (s == "Again").sum()),
        "accuracy": ("is_correct", "mean"),
        "avg_time": ("time_seconds", "mean"),
    }
    if "word" in df.columns:
        agg_dict["word"] = ("word", "first")
    if "pinyin" in df.columns:
        agg_dict["pinyin"] = ("pinyin", "first")
    if "meaning_es" in df.columns:
        agg_dict["meaning_es"] = ("meaning_es", "first")
    g = (
        df.groupby(["note_id", "card_type"])
        .agg(**agg_dict)
        .reset_index()
    )
    g = g[g["reviews"] >= min_reviews].sort_values(["accuracy", "agains"], ascending=[True, False])
    return g.head(top)


def most_lapsed_words(df: pd.DataFrame, min_lapses: int = 2, top: int = 25) -> pd.DataFrame:
    """Words with the most 'Again' responses, regardless of total reviews.

    Groups by note_id (not word) since same hanzi can represent different words.
    Includes word column for display (first word value per group).
    """
    agg_dict = {
        "reviews": ("is_correct", "size"),
        "agains": ("ease_label", lambda s: (s == "Again").sum()),
        "accuracy": ("is_correct", "mean"),
    }
    if "word" in df.columns:
        agg_dict["word"] = ("word", "first")
    g = (
        df.groupby(["note_id", "card_type"])
        .agg(**agg_dict)
        .reset_index()
    )
    g = g[g["agains"] >= min_lapses].sort_values("agains", ascending=False)
    return g.head(top)


def mastery_curve(df: pd.DataFrame, mastery_streak: int = 4,
                  consecutive_correct: Optional[int] = None) -> pd.DataFrame:
    """Reviews needed to reach mastery (N consecutive correct answers).

    Only considers review-type reviews (type==1, label "review") for mastery calculation.
    reviews_to_mastery is the position (review number) where mastery was reached,
    not the consecutive_correct count.

    Args:
        df: Reviews dataframe.
        mastery_streak: Number of consecutive correct answers required for mastery.
        consecutive_correct: Deprecated alias for mastery_streak (backward compat).
    """
    if df.empty:
        return pd.DataFrame()
    # Backward compatibility: consecutive_correct overrides mastery_streak
    if consecutive_correct is not None:
        mastery_streak = consecutive_correct
    # Only consider review-type reviews (type==2 in review_type column)
    if "review_type" in df.columns:
        reviews_only = df[df["review_type"] == "review"].copy()
    else:
        reviews_only = df.copy()
    if reviews_only.empty:
        return pd.DataFrame()

    results = []
    sorted_df = reviews_only.sort_values("review_datetime")
    for (note_id, card_type), group in sorted_df.groupby(["note_id", "card_type"]):
        streak = 0
        reviews_to_mastery = None
        position = 0
        for _, row in group.iterrows():
            position += 1
            if row["is_correct"]:
                streak += 1
                if streak >= mastery_streak and reviews_to_mastery is None:
                    reviews_to_mastery = position
            else:
                streak = 0
        total = len(group)
        acc = group["is_correct"].mean()
        max_streak = _max_consecutive(group["is_correct"].values)
        entry = {
            "note_id": note_id,
            "card_type": card_type,
            "total_reviews": total,
            "accuracy": acc,
            "reviews_to_mastery": reviews_to_mastery,
            "max_consecutive_correct": max_streak,
            "mastered": reviews_to_mastery is not None,
        }
        # Add word column for display when available
        if "word" in group.columns:
            entry["word"] = group["word"].iloc[0]
        results.append(entry)
    return pd.DataFrame(results)


def _max_consecutive(arr) -> int:
    """Maximum streak of True values in a boolean array."""
    max_streak = 0
    current = 0
    for v in arr:
        if v:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def lapse_history(df: pd.DataFrame) -> pd.DataFrame:
    """Track when each lapse occurred, to identify receding patterns."""
    lapses_df = df[df["ease_label"] == "Again"].copy()
    if lapses_df.empty:
        cols = ["note_id", "card_type", "lapse_date", "lapse_number"]
        if "word" in df.columns:
            cols.append("word")
        return pd.DataFrame(columns=cols)
    result = []
    has_word = "word" in lapses_df.columns
    for (note_id, card_type), group in lapses_df.sort_values("review_datetime").groupby(["note_id", "card_type"]):
        word_val = group["word"].iloc[0] if has_word else None
        for i, (_, row) in enumerate(group.iterrows(), 1):
            entry = {
                "note_id": note_id,
                "card_type": card_type,
                "lapse_date": row["review_datetime"].date(),
                "lapse_number": i,
                "day_of_week": row["review_datetime"].day_name(),
            }
            if has_word:
                entry["word"] = word_val
            result.append(entry)
    return pd.DataFrame(result)


def words_needing_attention(df: pd.DataFrame, cards_df: Optional[pd.DataFrame] = None,
                            min_reviews: int = 5) -> pd.DataFrame:
    """Identify words that currently need focused attention.

    Groups by (note_id, card_type) since the same word can be tested in
    different ways with different difficulty.  Also incorporates cards_df
    data when available to check relearning queue and ease factor.

    Criteria (any of):
      - Accuracy < 60% with ≥min_reviews
      - Currently in relearning queue (from cards snapshot)
      - 3+ Fallos total
      - Ease factor < 200 (from cards snapshot)
    """
    agg_dict = {
        "reviews": ("is_correct", "size"),
        "accuracy": ("is_correct", "mean"),
        "agains": ("ease_label", lambda s: (s == "Again").sum()),
        "last_review": ("review_datetime", "max"),
    }
    if "word" in df.columns:
        agg_dict["word"] = ("word", "first")
    if "pinyin" in df.columns:
        agg_dict["pinyin"] = ("pinyin", "first")
    if "meaning_es" in df.columns:
        agg_dict["meaning_es"] = ("meaning_es", "first")
    word_stats = (
        df.groupby(["note_id", "card_type"])
        .agg(**agg_dict)
        .reset_index()
    )

    issues = []
    has_word = "word" in word_stats.columns
    for _, row in word_stats.iterrows():
        if row["reviews"] < min_reviews:
            continue
        reasons = []
        if row["accuracy"] < LOW_ACCURACY:
            reasons.append(f"baja precisión ({row['accuracy']:.0%})")
        if row["agains"] >= 3:
            reasons.append(f"{int(row['agains'])} Fallos")
        if row["accuracy"] < CRITICAL_ACCURACY and row["reviews"] >= 10:
            reasons.append("crítica")

        # Check cards_df for additional issues (join by note_id + card_type)
        if cards_df is not None and "note_id" in cards_df.columns:
            card_match = cards_df[
                (cards_df["note_id"] == row["note_id"]) &
                (cards_df["card_type"] == row["card_type"])
            ]
            if not card_match.empty:
                # Check relearning by type field (type==3 means relearning)
                if "type" in card_match.columns:
                    if (card_match["type"] == 3).any():
                        reasons.append("en relearning")
                # Also check queue_label as fallback
                elif "queue_label" in card_match.columns:
                    if card_match["queue_label"].str.contains("relearning", na=False).any():
                        reasons.append("en relearning")
                # Check low ease factor
                if "ease_factor_percent" in card_match.columns:
                    ease_vals = card_match["ease_factor_percent"]
                    if (ease_vals < 200).any():
                        reasons.append("ease factor bajo")

        if reasons:
            # Determine priority
            priority = "media"
            if "crítica" in reasons or "en relearning" in reasons:
                priority = "alta"
            entry = {
                "note_id": row["note_id"],
                "reviews": int(row["reviews"]),
                "accuracy": row["accuracy"],
                "agains": int(row["agains"]),
                "last_review": row["last_review"].strftime("%Y-%m-%d"),
                "reasons": ", ".join(reasons),
                "priority": priority,
            }
            if has_word:
                entry["word"] = row["word"]
            issues.append(entry)

    result = pd.DataFrame(issues)
    if result.empty:
        return result
    # Sort: alta first, then by accuracy (worst first)
    priority_order = {"alta": 0, "media": 1, "baja": 2}
    result["priority_sort"] = result["priority"].map(priority_order).fillna(3)
    return result.sort_values(["priority_sort", "accuracy"], ascending=[True, True]).drop(columns=["priority_sort"])


# --- linguistic analysis -------------------------------------------------

def tone_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze accuracy by tone pattern, using pinyin_to_numbered() to extract tones.

    Restricted to card types that ask the user to write or recognize pinyin
    (H2P, M2P, HM2P) since tone perception is only tested on those cards.

    Uses utilities.pinyin_to_numbered() to convert accent-marked pinyin to
    numbered form (e.g., "àihào" → "ai4hao4"), then extracts tone numbers.
    Tone patterns use "-" as separator (displayed as "→").
    """
    if "pinyin" not in df.columns:
        return pd.DataFrame()
    df_work = df[df["card_type"].isin(PINYIN_OUTPUT_CARD_TYPES)].copy()
    if "pinyin" not in df_work.columns or df_work["pinyin"].notna().sum() == 0:
        return pd.DataFrame()
    df_work = df_work[df_work["pinyin"].notna() & (df_work["pinyin"] != "")].copy()
    if df_work.empty:
        return pd.DataFrame()

    def extract_tone_pattern(pinyin_str):
        numbered = pinyin_to_numbered(str(pinyin_str))
        if not numbered:
            return None
        tones = _NUMBERED_TONE_RE.findall(numbered)
        if not tones:
            return None
        return "-".join(tones)

    df_work["tone_pattern"] = df_work["pinyin"].apply(extract_tone_pattern)
    df_work = df_work.dropna(subset=["tone_pattern"])
    if df_work.empty:
        return pd.DataFrame()

    g = (
        df_work.groupby("tone_pattern")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )
    # Drop patterns seen fewer than MIN_GROUP_REVIEWS times: they are noise.
    g = g[g["reviews"] >= MIN_GROUP_REVIEWS]
    return g.sort_values("accuracy")


def character_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    """Break words into individual characters and analyze per-character accuracy.

    Restricted to card types where the hanzi is the target (M2H, PM2H, P2H),
    i.e. cards that ask the user to draw or recognize the character.

    Uses explode for performance instead of iterrows.
    """
    df_work = df[df["card_type"].isin(HANZI_TARGET_CARD_TYPES)][["word", "is_correct", "card_type"]].copy()
    df_work["word"] = df_work["word"].astype(str)

    # Split each word into individual characters
    chars_list = df_work["word"].apply(list)
    exploded = df_work.assign(char=chars_list).explode("char")

    # Filter to CJK Unified Ideographs only
    cjk_mask = exploded["char"].apply(lambda c: "\u4e00" <= c <= "\u9fff" if len(c) == 1 else False)
    char_df = exploded[cjk_mask]

    if char_df.empty:
        return pd.DataFrame()

    g = (
        char_df.groupby("char")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )
    # Drop characters seen fewer than MIN_GROUP_REVIEWS times: they are noise.
    g = g[g["reviews"] >= MIN_GROUP_REVIEWS]
    return g.sort_values("accuracy")


# --- response time analysis ----------------------------------------------

def response_time_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze response time by card type and accuracy.

    Uses groupby + unstack instead of lambda with DataFrame masking.
    """
    # Create a pivot-style aggregation
    time_pivot = (
        df.groupby(["card_type", "is_correct"])["time_seconds"]
        .mean()
        .unstack(fill_value=0)
    )

    result = df.groupby("card_type").agg(
        overall_avg=("time_seconds", "mean"),
        reviews=("time_seconds", "size"),
    ).reset_index()

    if 1 in time_pivot.columns:
        result["avg_time_correct"] = result["card_type"].map(time_pivot[1]).fillna(0)
    else:
        result["avg_time_correct"] = 0

    if 0 in time_pivot.columns:
        result["avg_time_incorrect"] = result["card_type"].map(time_pivot[0]).fillna(0)
    else:
        result["avg_time_incorrect"] = 0

    return result


# --- recommendations engine ----------------------------------------------

def generate_recommendations(df: pd.DataFrame, cards_df: Optional[pd.DataFrame] = None,
                             today: Optional[date] = None) -> list:
    """Generate personalized study recommendations based on data analysis.

    Works on copies of dataframes to avoid modifying originals.
    """
    recommendations = []

    if df.empty:
        return [{"type": "info", "message": "Aún no hay datos de repasos. Estudia unos días y vuelve a generar el informe."}]

    ov = overview(df, today=today)

    # 0. Data sufficiency guard
    insufficient = ov["active_days"] < MIN_ACTIVE_DAYS_FOR_RECS or ov["total_reviews"] < MIN_REVIEWS_FOR_RECS
    # With insufficient data, every recommendation is downgraded to low priority.
    prio = lambda p: "low" if insufficient else p

    # 1. Overall accuracy check
    if ov["overall_accuracy"] < WEAK_SKILL_ACCURACY:
        recommendations.append({
            "type": "alert",
            "priority": prio("high"),
            "title": "Precisión general baja",
            "message": f"Tu precisión global es {ov['overall_accuracy']:.0%}. Considera reducir el número de tarjetas nuevas por día y enfocarte en repasos.",
        })
    elif ov["overall_accuracy"] >= EXCELLENT_ACCURACY:
        recommendations.append({
            "type": "success",
            "priority": "low",
            "title": "Excelente precisión",
            "message": f"Tu precisión global es {ov['overall_accuracy']:.0%}. ¡Vas muy bien! Puedes considerar aumentar el ritmo de tarjetas nuevas.",
        })

    # 2. Weak skills
    by_type = accuracy_by(df, "card_type")
    weak = by_type[by_type["accuracy"] < WEAK_SKILL_ACCURACY]
    if not weak.empty:
        skills = ", ".join(f"{r['card_type']} ({r['accuracy']:.0%})" for _, r in weak.iterrows())
        recommendations.append({
            "type": "warning",
            "priority": prio("medium"),
            "title": "Habilidades débiles detectadas",
            "message": f"Estas habilidades tienen precisión < 70%: {skills}",
            "action": "Crea un mazo filtrado con: (" + " OR ".join(f"card:{r['card_type']}" for _, r in weak.iterrows()) + ")",
        })

    # 3. Hardest words
    hard = hardest_words(df, min_reviews=5, top=10)
    critical = hard[hard["accuracy"] < CRITICAL_ACCURACY]
    if not critical.empty:
        recommendations.append({
            "type": "warning",
            "priority": prio("high"),
            "title": "Palabras críticamente difíciles",
            "message": f"{len(critical)} combinaciones palabra/tipo tienen precisión < 50% con al menos {MIN_GROUP_REVIEWS} repasos.",
            "action": "Crea un mazo filtrado para estas palabras específicas y revísalas diariamente.",
        })

    # 4. Streak advice
    if not ov.get("streak_alive", True) and ov["total_reviews"] > 0:
        ended_str = f" (última sesión: {ov.get('last_streak_ended', 'desconocida')})" if ov.get("last_streak_ended") else ""
        recommendations.append({
            "type": "info",
            "priority": prio("medium"),
            "title": "Racha de estudio rota",
            "message": f"Has perdido la racha de estudio{ended_str}. ¡Recupérala con una sesión hoy!",
        })
    elif ov.get("current_streak", 0) >= 7 and ov.get("streak_alive", False):
        recommendations.append({
            "type": "success",
            "priority": "low",
            "title": "Buena racha de estudio",
            "message": f"Llevas {ov['current_streak']} días consecutivos estudiando. ¡Sigue así!",
        })

    # 5. Ease hell detection - check for LOW ease (<=150%), not high ease
    # Skip if FSRS data is present
    if cards_df is not None and "ease_factor_percent" in cards_df.columns:
        # Check if FSRS data is present and has actual data
        has_fsrs = False
        for col in ["fsrs_stability", "fsrs_difficulty"]:
            if col in cards_df.columns:
                fsrs_vals = pd.to_numeric(cards_df[col], errors="coerce")
                if fsrs_vals.notna().sum() > 0:
                    has_fsrs = True
                    break

        if not has_fsrs:
            cards_copy = cards_df.copy()
            cards_copy["ease_num"] = pd.to_numeric(cards_copy["ease_factor_percent"], errors="coerce")
            ease_hell = cards_copy[cards_copy["ease_num"] <= EASE_HELL]
            if len(ease_hell) > 10:
                recommendations.append({
                    "type": "alert",
                    "priority": prio("medium"),
                    "title": "Posible ease hell detectado",
                    "message": f"{len(ease_hell)} tarjetas tienen ease factor <= {EASE_HELL}%. Esto significa que los intervalos crecen muy lentamente, lo que puede ralentizar tu progreso.",
                    "action": "Revisa estas tarjetas y considera si necesitas más práctica con ellas o si deberían ser eliminadas.",
                })

    # 6. Review load check
    if ov["avg_reviews_per_active_day"] > 200:
        recommendations.append({
            "type": "info",
            "priority": prio("medium"),
            "title": "Carga de repasos alta",
            "message": f"Promedio de {ov['avg_reviews_per_active_day']:.0f} repasos por día activo. Si te resulta abrumador, reduce las nuevas.",
        })

    # 7. Time per review
    if ov["avg_time_per_review"] > 15:
        recommendations.append({
            "type": "info",
            "priority": "low",
            "title": "Tiempo de respuesta alto",
            "message": f"Promedio {ov['avg_time_per_review']:.1f}s por repaso. Si supera 15s, puede indicar que las tarjetas son complejas o que necesitas más práctica.",
        })

    # Sort by priority, then pin the data-sufficiency warning at the top so it
    # is never displaced by higher-priority items.
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 3))
    if insufficient:
        recommendations.insert(0, {
            "type": "info",
            "priority": "low",
            "title": "Datos aún escasos",
            "message": f"Datos aún escasos ({ov['active_days']} días activos, {ov['total_reviews']} repasos): las recomendaciones son orientativas.",
        })

    return recommendations


# --- chart rendering ----------------------------------------------------

def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _style_ax(ax, x_grid: bool = False) -> None:
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="x" if x_grid else "y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _accuracy_color(acc: float) -> str:
    if acc >= 0.9:
        return ACCURACY_COLORS["excellent"]
    if acc >= 0.75:
        return ACCURACY_COLORS["good"]
    if acc >= 0.6:
        return ACCURACY_COLORS["fair"]
    return ACCURACY_COLORS["poor"]


def chart_accuracy_by_card_type(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(g) + 1))
    labels = [
        f"{t} · {CARD_TYPE_DESCRIPTIONS.get(t, t)}" for t in g["card_type"]
    ]
    colors = [_accuracy_color(acc) for acc in g["accuracy"]]
    bars = ax.barh(labels, g["accuracy"] * 100, color=colors, height=0.55, zorder=3)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Precisión (%)")
    _style_ax(ax, x_grid=True)
    for bar, acc, n in zip(bars, g["accuracy"], g["reviews"]):
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{acc * 100:.0f}% (n={n})", va="center", fontsize=9, color=INK_SECONDARY)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_daily_reviews(daily: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    ax.bar(daily["review_datetime"], daily["reviews"], color=SEQUENTIAL_BLUE[2], width=0.85, zorder=3, alpha=0.8)
    ax.set_ylabel("Repasos / día")
    _style_ax(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_accuracy_trend(daily: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    ax.plot(daily["review_datetime"], daily["accuracy_7d"] * 100, color=BLUE, linewidth=2.2, zorder=3)
    ax.fill_between(daily["review_datetime"], daily["accuracy_7d"] * 100, alpha=0.1, color=BLUE)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Precisión media 7 días (%)")
    _style_ax(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_retention(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.6, 3))
    # Use proper bucket labels with reliability markers
    labels = []
    bar_colors = []
    for _, row in g.iterrows():
        label = str(row["bucket"])
        if not row.get("reliable", True):
            label += " *"
        labels.append(label)
        bar_colors.append(_accuracy_color(row["accuracy"]))
    bars = ax.bar(labels, g["accuracy"] * 100, color=bar_colors, zorder=3)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Precisión (%)")
    ax.set_xlabel("Intervalo desde el repaso anterior")
    _style_ax(ax)
    for bar, n in zip(bars, g["reviews"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"n={n}",
                ha="center", fontsize=8, color=INK_SECONDARY)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_weekday(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.6, 3))
    colors = [_accuracy_color(acc) for acc in g["accuracy"]]
    ax.bar(g["weekday"], g["accuracy"] * 100, color=colors, zorder=3)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Precisión (%)")
    _style_ax(ax)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_hour(hour_df: pd.DataFrame) -> str:
    """Bar chart of reviews per hour, with accuracy (n>=5 only) on a second axis."""
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    hours = hour_df["hour"].astype(int).tolist()
    reviews = hour_df["reviews"].tolist()
    ax.bar(hours, reviews, color=SEQUENTIAL_BLUE[2], width=0.7, zorder=3, alpha=0.8)
    ax.set_xlabel("Hora del día")
    ax.set_ylabel("Repasos")
    ax.set_xticks(hours)

    # Accuracy as a secondary axis, only for hours with at least 5 reviews.
    valid = hour_df[hour_df["reviews"] >= MIN_GROUP_REVIEWS]
    if not valid.empty:
        ax2 = ax.twinx()
        ax2.plot(
            valid["hour"].astype(int).tolist(),
            [a * 100 for a in valid["accuracy"]],
            color=RED, marker="o", markersize=4, linewidth=1.5, zorder=4,
        )
        ax2.set_ylabel("Precisión (%)")
        ax2.set_ylim(0, 105)
        ax2.tick_params(axis="y", colors=RED)

    _style_ax(ax)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_response_time_by_type(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    x = range(len(g))
    width = 0.35
    ax.bar([i - width / 2 for i in x], g["avg_time_correct"], width, label="Correcto", color=GREEN, alpha=0.8, zorder=3)
    ax.bar([i + width / 2 for i in x], g["avg_time_incorrect"], width, label="Incorrecto", color=RED, alpha=0.8, zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(g["card_type"], rotation=30, ha="right")
    ax.set_ylabel("Tiempo medio (segundos)")
    ax.legend(fontsize=9)
    _style_ax(ax)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_mastery_distribution(mastery_df: pd.DataFrame, mastery_streak: int = 4) -> str:
    """Pie chart of mastered vs. not mastered word/card combos."""
    fig, ax = plt.subplots(figsize=(4, 4))
    mastered = mastery_df["mastered"].sum()
    not_mastered = (~mastery_df["mastered"]).sum()
    if mastered + not_mastered == 0:
        return ""
    sizes = [mastered, not_mastered]
    labels = [f"Dominadas ({mastered})", f"No dominadas ({not_mastered})"]
    colors = [GREEN, ORANGE]
    ax.pie(sizes, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90)
    ax.set_title(f"Dominio ({mastery_streak} aciertos consecutivos)")
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_hard_words(hard_df: pd.DataFrame, top: int = 15, min_reviews: int = 3) -> str:
    """Horizontal bar chart of hardest words."""
    top_words = hard_df.head(top)
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(top_words) + 1))
    labels = []
    for _, r in top_words.iterrows():
        word = r.get("word", str(r["note_id"]))
        labels.append(f"{word} ({r['card_type']})")
    colors = [_accuracy_color(acc) for acc in top_words["accuracy"]]
    bars = ax.barh(labels, top_words["accuracy"] * 100, color=colors, height=0.55, zorder=3)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Precisión (%)")
    ax.set_title(f"Palabras más difíciles (mín. {min_reviews} repasos)")
    ax.invert_yaxis()
    _style_ax(ax, x_grid=True)
    for bar, acc, agains in zip(bars, top_words["accuracy"], top_words["agains"]):
        label = f"{acc * 100:.0f}%"
        if agains > 0:
            label += f" ({int(agains)} fallos)"
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=8, color=INK_SECONDARY)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


# --- HTML assembly --------------------------------------------------------

_PAGE_CSS = f"""
body {{ background:{SURFACE}; color:{INK_PRIMARY}; font-family: 'Segoe UI', Arial, sans-serif;
        max-width: 920px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
h1 {{ font-size: 1.6rem; margin-bottom: 0.2rem; }}
h2 {{ font-size: 1.15rem; margin-top: 2.5rem; border-bottom: 1px solid {GRID}; padding-bottom: 0.3rem; }}
h3 {{ font-size: 1rem; color: {INK_SECONDARY}; margin-top: 1.5rem; }}
.subtitle {{ color:{INK_SECONDARY}; margin-top: 0; }}
.stats-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin: 1rem 0; }}
.stat-tile {{ background:{SURFACE}; border:1px solid {GRID}; border-radius: 8px;
              padding: 0.75rem 1rem; }}
.stat-tile .value {{ font-size: 1.3rem; font-weight: 600; }}
.stat-tile .label {{ color:{INK_SECONDARY}; font-size: 0.8rem; }}
img.chart {{ max-width: 100%; display: block; margin: 0.75rem 0; border-radius: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.88rem; margin: 0.5rem 0; }}
th, td {{ text-align: left; padding: 0.4rem 0.7rem; border-bottom: 1px solid {GRID}; }}
th {{ color:{INK_SECONDARY}; font-weight: 600; }}
.muted {{ color:{INK_MUTED}; font-size: 0.85rem; }}
.rec-box {{ border-left: 4px solid {BLUE}; padding: 0.75rem 1rem; margin: 0.75rem 0;
            background: rgba(42,120,214,0.05); border-radius: 0 6px 6px 0; }}
.rec-box.alert {{ border-left-color: {RED}; background: rgba(192,57,43,0.05); }}
.rec-box.warning {{ border-left-color: {ORANGE}; background: rgba(230,126,34,0.05); }}
.rec-box.success {{ border-left-color: {GREEN}; background: rgba(39,174,96,0.05); }}
.rec-title {{ font-weight: 600; margin-bottom: 0.25rem; }}
.rec-action {{ color:{BLUE}; font-weight: 500; margin-top: 0.3rem; }}
.badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }}
.badge-alta {{ background: rgba(192,57,43,0.15); color: {RED}; }}
.badge-media {{ background: rgba(230,126,34,0.15); color: {ORANGE}; }}
.badge-baja {{ background: rgba(39,174,96,0.15); color: {GREEN}; }}
"""


def _stat_tile(value: str, label: str) -> str:
    return f'<div class="stat-tile"><div class="value">{value}</div><div class="label">{label}</div></div>'


def _empty_report_html() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Informe de aprendizaje</title><style>{_PAGE_CSS}</style></head><body>"
        "<h1>Informe de aprendizaje</h1>"
        "<p>Todavía no hay repasos en el CSV exportado. Estudia unos días en Anki, "
        "sincroniza con AnkiWeb, corre <code>zhongwen-anki-export-stats</code> de nuevo "
        "y vuelve a generar este informe.</p></body></html>"
    )


def _table_html(df: pd.DataFrame, columns: dict, max_rows: Optional[int] = None) -> str:
    """Generate HTML table. *columns* maps df column -> (header label, formatter, raw_html?).

    Formatter can return raw HTML (for badges) if the third element of the tuple is True.
    When raw_html is True, the cell content is NOT escaped.
    """
    data = df.head(max_rows) if max_rows else df
    head = "".join(f"<th>{html_module.escape(label)}</th>" for label, _, _ in columns.values())
    rows = []
    for _, row in data.iterrows():
        cells = "".join(
            f"<td>{fmt(row[col]) if raw else html_module.escape(str(fmt(row[col])))}</td>"
            for col, (_, fmt, raw) in columns.items()
        )
        rows.append(f"<tr>{cells}</tr>")
    footer = ""
    if max_rows and len(df) > max_rows:
        footer = f'<tr><td colspan="{len(columns)}" class="muted">... y {len(df) - max_rows} más</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}{footer}</tbody></table>"


def _rec_html(rec: dict) -> str:
    cls = rec.get("type", "info")
    title = html_module.escape(rec.get("title", "Sugerencia"))
    msg = html_module.escape(rec["message"])
    action = rec.get("action", "")
    action_html = f'<div class="rec-action">Acción: {html_module.escape(action)}</div>' if action else ""
    return (
        f'<div class="rec-box {cls}">'
        f'<div class="rec-title">{title}</div>'
        f'<div>{msg}</div>'
        f"{action_html}"
        f"</div>"
    )


def build_report_html(df: pd.DataFrame, cards_df: Optional[pd.DataFrame] = None,
                      min_reviews: int = 3, mastery_streak: int = 4,
                      today: Optional[date] = None) -> str:
    """Build the full HTML report.

    Filters the input dataframe internally: user answers only, then excludes
    info-only card types for accuracy metrics.

    Args:
        df: Reviews dataframe.
        cards_df: Optional card snapshot dataframe.
        min_reviews: Minimum reviews for hardest-words table.
        mastery_streak: Consecutive correct answers needed for mastery.
        today: Reference date for streak calculation (for testing).
    """
    # Filter to user answers only
    df_user = filter_user_answers(df)

    # Exclude info-only card type from accuracy analysis
    df_accuracy = exclude_info_only(df_user)

    if df_user.empty:
        return _empty_report_html()

    # C.1: Use df_user for volume metrics, df_accuracy for precision only
    ov = overview(df_user, today=today)
    if df_accuracy.empty:
        ov["overall_accuracy"] = float("nan")
    else:
        ov["overall_accuracy"] = df_accuracy["is_correct"].mean()
    if ov["total_reviews"] == 0:
        return _empty_report_html()

    # Compute all metrics using filtered data
    by_card_type = accuracy_by(df_accuracy, "card_type")
    by_level = accuracy_by(df_accuracy, "level")
    daily = daily_trend(df_user)
    retention = retention_by_interval(df_user)
    weekday = accuracy_by_weekday(df_accuracy)
    hour = accuracy_by_hour(df_user)
    hard = hardest_words(df_accuracy, min_reviews=min_reviews)
    most_lapsed = most_lapsed_words(df_accuracy, min_lapses=2)
    mastery = mastery_curve(df_accuracy, mastery_streak=mastery_streak)
    attn = words_needing_attention(df_accuracy, cards_df, min_reviews=5)
    tone = tone_analysis(df_accuracy)
    char_diff = character_difficulty(df_accuracy)
    resp_time = response_time_analysis(df_accuracy)
    recommendations = generate_recommendations(df_accuracy, cards_df, today=today)

    # Accuracy note for info-only card type
    accuracy_note = "<p class='muted'>La tarjeta <em>Toda la información</em> (consulta) no cuenta en la precisión.</p>"

    # Pinyin/meaning enrichment is only present when the export used --vocab-dir.
    has_pinyin_info = "pinyin" in df.columns and "meaning_es" in df.columns

    def _pinyin_cell(row):
        parts = []
        p = str(row.get("pinyin") or "").strip()
        m = str(row.get("meaning_es") or "").strip()
        if p:
            parts.append(p)
        if m:
            parts.append(m)
        return " · ".join(parts)

    # --- Stats tiles ---
    # C.3: Streak tile — current=0 when broken, separate max streak tile
    if ov.get("streak_alive", True):
        current_streak_display = f"🔥 {ov['current_streak']}"
    else:
        last_date = ov.get("last_streak_ended", "")
        if last_date:
            current_streak_display = f"0 (última sesión: {last_date})"
        else:
            current_streak_display = "0"
    accuracy_display = f"{ov['overall_accuracy'] * 100:.0f}%" if not (isinstance(ov['overall_accuracy'], float) and ov['overall_accuracy'] != ov['overall_accuracy']) else "—"  # NaN check
    stats = "".join([
        _stat_tile(f"{ov['total_reviews']:,}", "Repasos totales"),
        _stat_tile(f"{ov['unique_words']:,}", "Notas distintas"),
        _stat_tile(f"{accuracy_display}", "Precisión global"),
        _stat_tile(f"{ov['total_time_hours']:.1f} h", "Tiempo total"),
        _stat_tile(f"{ov['active_days']} / {ov['span_days']}", "Días activos / periodo"),
        _stat_tile(f"{ov['avg_reviews_per_active_day']:.0f}", "Repasos/día activo"),
        _stat_tile(f"{ov['avg_time_per_review']:.1f}s", "Tiempo/repaso"),
        _stat_tile(current_streak_display, "Racha actual"),
        _stat_tile(f"🔥 {ov['longest_streak']}", "Racha máxima"),
    ])

    # --- Recommendations ---
    rec_section = ""
    if recommendations:
        recs_html = "".join(_rec_html(r) for r in recommendations)
        rec_section = f"<h2>💡 Recomendaciones personalizadas</h2>{recs_html}"

    # --- Card type accuracy ---
    card_type_section = (
        "<h2>Precisión por tipo de tarjeta</h2>"
        "<p class='muted'>En qué habilidad conviene incidir. Cada código indica qué se muestra y qué "
        "se pide: H = hanzi, P = pinyin, M = significado (p. ej. PM2H: pinyin + significado → dibujar hanzi).</p>"
        f"<img class='chart' src='{chart_accuracy_by_card_type(by_card_type)}' alt='Precisión por tipo de tarjeta'>"
        f"{accuracy_note}"
    )

    # --- Level section ---
    level_section = ""
    if by_level["level"].nunique() > 1:
        level_sorted = by_level.sort_values("level", key=lambda s: s.map(_level_sort_key))
        level_rows = "".join(
            f"<tr><td>{html_module.escape(str(row['level']))}</td><td>{int(row['reviews'])}</td>"
            f"<td>{float(row['accuracy']) * 100:.0f}%</td><td>{float(row['avg_time_s']):.1f}s</td></tr>"
            for _, row in level_sorted.iterrows()
        )
        level_section = (
            "<h2>Precisión por nivel</h2>"
            "<table><thead><tr><th>Nivel</th><th>Repasos</th><th>Precisión</th><th>Tiempo medio</th></tr></thead>"
            f"<tbody>{level_rows}</tbody></table>"
        )

    # --- Daily trends ---
    daily_section = (
        "<h2>Volumen de repasos por día</h2>"
        f"<img class='chart' src='{chart_daily_reviews(daily)}' alt='Repasos por día'>"
        "<h2>Tendencia de precisión (media móvil 7 días)</h2>"
        f"<img class='chart' src='{chart_accuracy_trend(daily)}' alt='Tendencia de precisión'>"
    )

    # --- Retention ---
    retention_section = ""
    if not retention.empty:
        retention_section = (
            "<h2>Retención por intervalo</h2>"
            "<p class='muted'>Precisión en repasos programados (no en pasos de aprendizaje), "
            "agrupada por cuánto tiempo había pasado desde el repaso anterior. Si baja mucho en "
            "los intervalos largos, Anki está espaciando demasiado agresivo para ese contenido. "
            "Buckets marcados con * tienen muestra pequeña (n<5) y son menos fiables.</p>"
            f"<img class='chart' src='{chart_retention(retention)}' alt='Retención por intervalo'>"
        )
    else:
        retention_section = (
            "<h2>Retención por intervalo</h2>"
            "<p class='muted'>Aún no hay repasos programados (tipo <em>review</em>): todas las tarjetas "
            "siguen en aprendizaje. Esta sección aparecerá cuando Anki empiece a espaciar repasos.</p>"
        )

    # --- Weekday ---
    weekday_section = ""
    if not weekday.empty:
        weekday_section = (
            "<h2>Precisión por día de la semana</h2>"
            f"<img class='chart' src='{chart_weekday(weekday)}' alt='Precisión por día de la semana'>"
        )

    # --- Hour - real matplotlib chart ---
    hour_section = ""
    if not hour.empty:
        hour_chart = chart_hour(hour)
        hour_section = (
            "<h2>Repasos y precisión por hora del día</h2>"
            "<p class='muted'>La línea de precisión solo se dibuja en horas con al menos "
            f"{MIN_GROUP_REVIEWS} repasos.</p>"
            f"<img class='chart' src='{hour_chart}' alt='Repasos y precisión por hora del día'>"
        )

    # --- Response time ---
    resp_section = ""
    if not resp_time.empty:
        resp_section = (
            "<h2>Tiempo de respuesta por habilidad</h2>"
            "<p class='muted'>Tiempo medio en responder correctamente vs. incorrectamente. "
            "Si el tiempo incorrecto es muy alto, puede indicar confusión (no solo olvido).</p>"
            f"<img class='chart' src='{chart_response_time_by_type(resp_time)}' alt='Tiempo de respuesta'>"
        )

    # --- Hard words ---
    hard_section = ""
    if not hard.empty:
        hard_chart = chart_hard_words(hard, min_reviews=min_reviews)
        hard_disp = hard.copy()
        hard_columns = {
            "word": ("Palabra", lambda v: str(v), False),
            "card_type": ("Tipo", str, False),
            "reviews": ("Repasos", int, False),
            "agains": ("Fallos (Again)", int, False),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
            "avg_time": ("Tiempo medio", lambda v: f"{v:.1f}s", False),
        }
        if has_pinyin_info:
            hard_disp["pinyin_meaning"] = hard_disp.apply(_pinyin_cell, axis=1)
            hard_columns["pinyin_meaning"] = ("Pinyin / significado", str, False)
        hard_table = _table_html(hard_disp, hard_columns)
        hard_section = (
            "<h2>🔴 Palabras más difíciles</h2>"
            "<p class='muted'>Las combinaciones nota/tipo con peor precisión "
            f"(mínimo {min_reviews} repasos). Candidatas prioritarias para repaso dirigido.</p>"
            f"<img class='chart' src='{hard_chart}' alt='Palabras más difíciles'>"
            f"{hard_table}"
        )

    # --- Most lapsed ---
    lapsed_section = ""
    if not most_lapsed.empty:
        lapsed_table = _table_html(most_lapsed.head(20), {
            "word": ("Palabra", lambda v: str(v), False),
            "card_type": ("Tipo", str, False),
            "agains": ("Fallos (Again)", int, False),
            "reviews": ("Repasos", int, False),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
        })
        recent_lapses = ""
        lapses_hist = lapse_history(df_accuracy)
        if not lapses_hist.empty:
            latest = lapses_hist.sort_values("lapse_date", ascending=False).head(20)
            recent_lapses = (
                "<h3>Últimos fallos</h3>"
                "<p class='muted'>Los 20 fallos (Again) más recientes: cuándo, qué palabra y de qué tipo.</p>"
                + _table_html(latest, {
                    "lapse_date": ("Fecha", str, False),
                    "word": ("Palabra", lambda v: str(v), False),
                    "card_type": ("Tipo", str, False),
                    "lapse_number": ("Nº de fallo", int, False),
                })
            )
        lapsed_section = (
            "<h3>📉 Palabras con más Fallos (Again) acumulados</h3>"
            f"{lapsed_table}"
            f"{recent_lapses}"
        )

    # --- Mastery ---
    mastery_section = ""
    if not mastery.empty:
        mastered_count = mastery["mastered"].sum()
        total_combos = len(mastery)
        mastery_chart = chart_mastery_distribution(mastery, mastery_streak=mastery_streak)
        mastery_img = f"<img class='chart' src='{mastery_chart}' alt='Distribución de dominio'>" if mastery_chart else ""
        mastery_stats = "".join([
            _stat_tile(str(mastered_count), "Combinaciones dominadas"),
            _stat_tile(str(total_combos - mastered_count), "Sin dominar"),
            _stat_tile(f"{mastered_count / total_combos * 100:.0f}%", "Tasa de dominio"),
        ])
        not_mastered = mastery[~mastery["mastered"]].sort_values("total_reviews", ascending=False).head(15)
        if not not_mastered.empty:
            mastery_table = _table_html(not_mastered, {
                "word": ("Palabra", lambda v: str(v), False),
                "card_type": ("Tipo", str, False),
                "total_reviews": ("Repasos", int, False),
                "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
                "max_consecutive_correct": ("Racha máxima", int, False),
            })
        else:
            mastery_table = "<p class='muted'>¡Todas las combinaciones están dominadas! 🎉</p>"
        mastery_section = (
            f"<h2>🎯 Curva de dominio</h2>"
            f"<p class='muted'>Dominio = {mastery_streak} aciertos consecutivos en el mismo tipo de tarjeta (solo repasos programados).</p>"
            f"<div class='stats-row'>{mastery_stats}</div>"
            f"{mastery_img}"
            f"<h3>Combinaciones que aún no dominan</h3>"
            f"{mastery_table}"
        )
    else:
        mastery_section = (
            f"<h2>🎯 Curva de dominio</h2>"
            f"<p class='muted'>Aún no hay repasos programados (tipo <em>review</em>) "
            f"con al menos {mastery_streak} aciertos consecutivos: no se puede calcular el dominio.</p>"
        )

    # --- Words needing attention ---
    attention_section = ""
    if not attn.empty:
        attn_disp = attn.copy()
        attn_columns = {
            "word": ("Palabra", lambda v: str(v), False),
            "priority": ("Prioridad", lambda v: f'<span class="badge badge-{v}">{v}</span>', True),
            "reviews": ("Repasos", int, False),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
            "agains": ("Fallos (Again)", int, False),
            "reasons": ("Motivo", str, False),
            "last_review": ("Último repaso", str, False),
        }
        if has_pinyin_info:
            attn_disp["pinyin_meaning"] = attn_disp.apply(_pinyin_cell, axis=1)
            attn_columns["pinyin_meaning"] = ("Pinyin / significado", str, False)
        attn_table = _table_html(attn_disp, attn_columns)
        attention_section = (
            "<h2>⚠️ Palabras que necesitan atención</h2>"
            "<p class='muted'>Palabras con precisión críticamente baja o muchos Fallos. "
            "Son las prioritarias para un repaso enfocado.</p>"
            f"{attn_table}"
        )

    # --- Linguistic analysis ---
    linguistic_section = ""
    if not tone.empty:
        tone_table = _table_html(tone.head(20), {
            "tone_pattern": ("Patrón tonal", lambda v: v.replace("-", " → "), False),
            "reviews": ("Repasos", int, False),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
        })
        linguistic_section += (
            "<h2>🔊 Análisis lingüístico</h2>"
            "<h3>Dificultad por patrón tonal</h3>"
            "<p class='muted'>Solo incluye tarjetas que piden escribir pinyin (H2P, M2P, HM2P) "
            f"y patrones con al menos {MIN_GROUP_REVIEWS} repasos. "
            "Los patrones con peor precisión indican combinaciones de tonos que cuestan más.</p>"
            f"{tone_table}"
        )
    else:
        if "pinyin" in df.columns:
            tone_empty_msg = (
                "Aún no hay repasos de tarjetas que piden escribir pinyin (H2P, M2P, HM2P). "
                "Esta sección aparecerá cuando empieces a estudiarlas."
            )
        else:
            tone_empty_msg = (
                "No hay datos de pinyin para analizar tonos. Exporta con "
                "<code>zhongwen-anki-export-stats --vocab-dir data</code> para incluir el pinyin."
            )
        linguistic_section += (
            "<h2>🔊 Análisis lingüístico</h2>"
            f"<p class='muted'>{tone_empty_msg}</p>"
        )

    if not char_diff.empty:
        char_table = _table_html(char_diff.head(20), {
            "char": ("Carácter", str, False),
            "reviews": ("Apariciones", int, False),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%", False),
        })
        linguistic_section += (
            "<h3>Caracteres más difíciles de escribir</h3>"
            "<p class='muted'>Solo incluye tarjetas que piden dibujar el hanzi (M2H, PM2H, P2H) "
            f"y caracteres vistos al menos {MIN_GROUP_REVIEWS} veces. "
            "Caracteres que aparecen en palabras con baja precisión pueden indicar dificultad intrínseca (trazos, confusión visual).</p>"
            f"{char_table}"
        )

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Informe de aprendizaje — Chino HSK</title>
<style>{_PAGE_CSS}</style>
</head><body>
<h1>Informe de aprendizaje — Chino HSK</h1>
<p class="subtitle">{ov['date_start']:%Y-%m-%d} → {ov['date_end']:%Y-%m-%d} · {ov['span_days']} días</p>
<div class="stats-row">{stats}</div>

{rec_section}

{card_type_section}
{level_section}

{daily_section}
{retention_section}
{weekday_section}
{hour_section}
{resp_section}

{hard_section}
{lapsed_section}

{mastery_section}
{attention_section}
{linguistic_section}

<hr style="margin:2rem 0;border:none;border-top:1px solid {GRID}">
<p class="muted">Generado con <code>zhongwen-anki-analyze-stats</code> · {datetime.now():%Y-%m-%d %H:%M}</p>
</body></html>"""


# --- CLI -----------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a comprehensive HTML learning report from exported Anki data."
    )
    parser.add_argument("-i", "--input", type=Path,
                         default=Path("docs/local/estadisticas/anki_reviews.csv"),
                         help="Reviews CSV exported by zhongwen-anki-export-stats.")
    parser.add_argument("-o", "--output", type=Path,
                         default=Path("docs/local/estadisticas/report.html"),
                         help="Output HTML report path.")
    parser.add_argument("--cards", type=Path, default=None,
                         help="Card snapshot CSV (--card-snapshot from export).")
    parser.add_argument("--min-reviews", type=int, default=3,
                         help="Minimum reviews for a word to appear in hardest-words table. Default: 3.")
    parser.add_argument("--mastery-streak", type=int, default=4,
                         help="Consecutive correct answers needed for mastery. Default: 4.")
    parser.add_argument("--today", type=str, default=None,
                         help="Reference date for streak calculation (YYYY-MM-DD). Useful for testing.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.input.exists():
        raise SystemExit(f"{args.input} not found. Run `zhongwen-anki-export-stats` first.")
    if args.cards is not None and not args.cards.exists():
        raise SystemExit(
            f"{args.cards} not found. Run `zhongwen-anki-export-stats --card-snapshot` first."
        )

    today = None
    if args.today:
        try:
            today = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit(f"Invalid --today date format: '{args.today}'. Expected YYYY-MM-DD.")

    df, cards = load(args.input, args.cards)
    report = build_report_html(
        df, cards,
        min_reviews=args.min_reviews,
        mastery_streak=args.mastery_streak,
        today=today,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote report -> {args.output}")


if __name__ == "__main__":
    main()
