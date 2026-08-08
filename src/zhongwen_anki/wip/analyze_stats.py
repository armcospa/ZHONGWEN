"""WORK IN PROGRESS -- not validated against real review data yet.

See `zhongwen_anki.wip` package docstring: this module can change shape or be
dropped. Once it's actually been run against a real `data/anki_reviews.csv`
and the report format is settled, promote it out of `wip/`.

Turn the CSV from `export_stats.py` into a self-contained HTML learning report.

Usage:
    zhongwen-anki-analyze-stats
    zhongwen-anki-analyze-stats -i data/anki_reviews.csv -o data/report.html

Intended workflow (most study happens on AnkiDroid, away from this repo):
    1. AnkiDroid -> sync -> AnkiWeb.
    2. Open Anki Desktop on the machine with this repo -> sync -> pulls the
       AnkiDroid reviews into the local collection.anki2.
    3. `zhongwen-anki-export-stats` (refreshes data/anki_reviews.csv).
    4. `zhongwen-anki-analyze-stats` (this script; rebuilds the HTML report).

Everything here is derived straight from the exported CSV with pandas; no
network access, no writing back to Anki.
"""
import argparse
import base64
import html
import io
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# --- palette -----------------------------------------------------------
# Fixed roles (not cycled) so the same concept always gets the same color
# across every chart in the report.
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"

# One fixed hue per card type (categorical, identity) -- reused in every
# chart that breaks results down by card type.
CARD_TYPE_COLORS = {
    "Hanzi -> Significado": "#2a78d6",
    "Significado -> Hanzi": "#eb6834",
    "Escribir Pinyin": "#1baf7a",
    "Escribir Hanzi": "#eda100",
}
DEFAULT_CARD_TYPE_COLOR = "#898781"

# Single-hue ramp, light->dark, for ordinal/magnitude series (e.g. retention
# by increasing interval length).
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]

WEEKDAY_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
WEEKDAY_ORDER = list(WEEKDAY_ES.values())

LEVEL_RE = re.compile(r"HSK\d+")

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
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


# --- loading -------------------------------------------------------------

def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["review_datetime"])
    if "card_type" not in df.columns:
        # CSV exported before card_type existed (see export_stats.py).
        df["card_type"] = "Desconocido"
    df["card_type"] = df["card_type"].fillna("Desconocido")
    df["level"] = df["deck"].fillna("").map(_level_from_deck)
    return df


def _level_from_deck(deck: str) -> str:
    m = LEVEL_RE.search(deck)
    return m.group() if m else "Sin nivel"


# --- metrics ---------------------------------------------------------------

def overview(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total_reviews": 0}
    span_days = (df["review_datetime"].max() - df["review_datetime"].min()).days + 1
    active_days = df["review_datetime"].dt.date.nunique()
    return {
        "total_reviews": len(df),
        "unique_words": df["word"].nunique(),
        "date_start": df["review_datetime"].min(),
        "date_end": df["review_datetime"].max(),
        "span_days": span_days,
        "active_days": active_days,
        "total_time_hours": df["time_seconds"].sum() / 3600,
        "overall_accuracy": df["is_correct"].mean(),
        "avg_reviews_per_active_day": len(df) / active_days if active_days else 0,
    }


def accuracy_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    g = (
        df.groupby(column)
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"),
             avg_time_s=("time_seconds", "mean"))
        .reset_index()
        .sort_values("accuracy")
    )
    return g


def daily_trend(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.set_index("review_datetime")
        .resample("D")
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
    )
    daily["accuracy_7d"] = daily["accuracy"].rolling(7, min_periods=1).mean()
    return daily.reset_index()


def retention_by_interval(df: pd.DataFrame) -> pd.DataFrame:
    # Only true spaced reviews (positive last_interval, measured in days);
    # excludes learning/relearning steps, where last_interval is negative
    # (seconds) and "retention" doesn't mean the same thing.
    reviewed = df[(df["review_type"] == "review") & (df["last_interval"] > 0)].copy()
    if reviewed.empty:
        return pd.DataFrame(columns=["bucket", "reviews", "accuracy"])
    bins = [0, 1, 3, 7, 30, 10**6]
    labels = ["<1d", "1-3d", "3-7d", "7-30d", "30d+"]
    reviewed["bucket"] = pd.cut(reviewed["last_interval"], bins=bins, labels=labels)
    return (
        reviewed.groupby("bucket", observed=True)
        .agg(reviews=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )


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


def hardest_words(df: pd.DataFrame, min_reviews: int = 3, top: int = 20) -> pd.DataFrame:
    g = (
        df.groupby(["word", "card_type"])
        .agg(
            reviews=("is_correct", "size"),
            lapses=("ease_label", lambda s: (s == "Again").sum()),
            accuracy=("is_correct", "mean"),
        )
        .reset_index()
    )
    g = g[g["reviews"] >= min_reviews].sort_values(["accuracy", "lapses"], ascending=[True, False])
    return g.head(top)


# --- chart rendering ---------------------------------------------------

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


def chart_accuracy_by_card_type(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.6, 0.7 * len(g) + 1))
    colors = [CARD_TYPE_COLORS.get(t, DEFAULT_CARD_TYPE_COLOR) for t in g["card_type"]]
    bars = ax.barh(g["card_type"], g["accuracy"] * 100, color=colors, height=0.55, zorder=3)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Precisión (%)")
    _style_ax(ax, x_grid=True)
    for bar, acc, n in zip(bars, g["accuracy"], g["reviews"]):
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                 f"{acc * 100:.0f}% (n={n})", va="center", fontsize=9, color=INK_SECONDARY)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_daily_reviews(daily: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    ax.bar(daily["review_datetime"], daily["reviews"], color=SEQUENTIAL_BLUE[2], width=0.85, zorder=3)
    ax.set_ylabel("Repasos / día")
    _style_ax(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_accuracy_trend(daily: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    ax.plot(daily["review_datetime"], daily["accuracy_7d"] * 100, color=BLUE, linewidth=2.2, zorder=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Precisión media 7 días (%)")
    _style_ax(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def chart_retention(g: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.6, 3))
    colors = SEQUENTIAL_BLUE[: len(g)]
    bars = ax.bar(g["bucket"].astype(str), g["accuracy"] * 100, color=colors, zorder=3)
    ax.set_ylim(0, 100)
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
    ax.bar(g["weekday"], g["accuracy"] * 100, color=BLUE, zorder=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Precisión (%)")
    _style_ax(ax)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


# --- HTML assembly -------------------------------------------------------

_PAGE_CSS = f"""
body {{ background:{SURFACE}; color:{INK_PRIMARY}; font-family: 'Segoe UI', Arial, sans-serif;
        max-width: 880px; margin: 2rem auto; padding: 0 1rem; line-height: 1.4; }}
h1 {{ font-size: 1.5rem; margin-bottom: 0.2rem; }}
h2 {{ font-size: 1.1rem; margin-top: 2.5rem; border-bottom: 1px solid {GRID}; padding-bottom: 0.3rem; }}
.subtitle {{ color:{INK_SECONDARY}; margin-top: 0; }}
.stats-row {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
.stat-tile {{ background:{SURFACE}; border:1px solid {GRID}; border-radius: 8px;
              padding: 0.75rem 1rem; min-width: 140px; }}
.stat-tile .value {{ font-size: 1.4rem; font-weight: 600; }}
.stat-tile .label {{ color:{INK_SECONDARY}; font-size: 0.8rem; }}
img.chart {{ max-width: 100%; display: block; margin: 0.5rem 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
th, td {{ text-align: left; padding: 0.35rem 0.6rem; border-bottom: 1px solid {GRID}; }}
th {{ color:{INK_SECONDARY}; font-weight: 600; }}
.muted {{ color:{INK_MUTED}; font-size: 0.85rem; }}
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


def _table_html(df: pd.DataFrame, columns: dict) -> str:
    """*columns* maps dataframe column -> (header label, formatter)."""
    head = "".join(f"<th>{html.escape(label)}</th>" for label, _ in columns.values())
    rows = []
    for _, row in df.iterrows():
        cells = "".join(
            f"<td>{html.escape(str(fmt(row[col])))}</td>" for col, (_, fmt) in columns.items()
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_report_html(df: pd.DataFrame, min_reviews: int = 3) -> str:
    ov = overview(df)
    if ov["total_reviews"] == 0:
        return _empty_report_html()

    by_card_type = accuracy_by(df, "card_type")
    by_level = accuracy_by(df, "level")
    daily = daily_trend(df)
    retention = retention_by_interval(df)
    weekday = accuracy_by_weekday(df)
    hard = hardest_words(df, min_reviews=min_reviews)

    stats = "".join([
        _stat_tile(f"{ov['total_reviews']:,}", "Repasos totales"),
        _stat_tile(f"{ov['unique_words']:,}", "Palabras distintas"),
        _stat_tile(f"{ov['overall_accuracy'] * 100:.0f}%", "Precisión global"),
        _stat_tile(f"{ov['total_time_hours']:.1f} h", "Tiempo total estudiado"),
        _stat_tile(f"{ov['active_days']} / {ov['span_days']}", "Días activos / periodo"),
        _stat_tile(f"{ov['avg_reviews_per_active_day']:.0f}", "Repasos por día activo"),
    ])

    level_section = ""
    if by_level["level"].nunique() > 1:
        level_rows = "".join(
            f"<tr><td>{html.escape(r.level)}</td><td>{r.reviews}</td><td>{r.accuracy * 100:.0f}%</td></tr>"
            for r in by_level.itertuples()
        )
        level_section = (
            "<h2>Precisión por nivel</h2>"
            f"<table><thead><tr><th>Nivel</th><th>Repasos</th><th>Precisión</th></tr></thead>"
            f"<tbody>{level_rows}</tbody></table>"
        )

    retention_section = ""
    if not retention.empty:
        retention_section = (
            "<h2>Retención por intervalo</h2>"
            "<p class='muted'>Precisión en repasos programados (no en pasos de aprendizaje), "
            "agrupada por cuánto tiempo había pasado desde el repaso anterior. Si baja mucho en "
            "los intervalos largos, Anki está espaciando demasiado agresivo para ese contenido.</p>"
            f"<img class='chart' src='{chart_retention(retention)}' alt='Retención por intervalo'>"
        )

    weekday_section = ""
    if not weekday.empty:
        weekday_section = (
            "<h2>Precisión por día de la semana</h2>"
            f"<img class='chart' src='{chart_weekday(weekday)}' alt='Precisión por día de la semana'>"
        )

    hard_section = ""
    if not hard.empty:
        hard_table = _table_html(hard, {
            "word": ("Palabra", str),
            "card_type": ("Tipo de tarjeta", str),
            "reviews": ("Repasos", int),
            "lapses": ("Fallos (Again)", int),
            "accuracy": ("Precisión", lambda v: f"{v * 100:.0f}%"),
        })
        hard_section = (
            "<h2>Palabras más difíciles</h2>"
            f"<p class='muted'>Las {len(hard)} combinaciones palabra/tipo de tarjeta con peor precisión "
            f"(mínimo {min_reviews} repasos). Son las mejores candidatas para repaso dirigido "
            "(mazo filtrado o tarjetas 'sanguijuela').</p>"
            f"{hard_table}"
        )

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Informe de aprendizaje</title><style>{_PAGE_CSS}</style></head><body>
<h1>Informe de aprendizaje</h1>
<p class="subtitle">{ov['date_start']:%Y-%m-%d} — {ov['date_end']:%Y-%m-%d}</p>
<div class="stats-row">{stats}</div>

<h2>Precisión por tipo de tarjeta</h2>
<p class="muted">En qué habilidad conviene incidir: lectura (Hanzi -> Significado), producción
(Significado -> Hanzi), ortografía (Escribir Pinyin) o escritura a mano (Escribir Hanzi).</p>
<img class="chart" src="{chart_accuracy_by_card_type(by_card_type)}" alt="Precisión por tipo de tarjeta">

{level_section}

<h2>Volumen de repasos por día</h2>
<img class="chart" src="{chart_daily_reviews(daily)}" alt="Repasos por día">

<h2>Tendencia de precisión (media móvil 7 días)</h2>
<img class="chart" src="{chart_accuracy_trend(daily)}" alt="Tendencia de precisión">

{retention_section}
{weekday_section}
{hard_section}
</body></html>"""


# --- CLI -------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an HTML learning report from the CSV exported by zhongwen-anki-export-stats."
    )
    parser.add_argument("-i", "--input", type=Path, default=Path("data/anki_reviews.csv"))
    parser.add_argument("-o", "--output", type=Path, default=Path("data/report.html"))
    parser.add_argument(
        "--min-reviews", type=int, default=3,
        help="Minimum reviews for a word/card-type pair to appear in the 'hardest words' table.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.input.exists():
        raise SystemExit(f"{args.input} not found. Run `zhongwen-anki-export-stats` first.")
    df = load(args.input)
    report = build_report_html(df, min_reviews=args.min_reviews)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote report -> {args.output}")


if __name__ == "__main__":
    main()
