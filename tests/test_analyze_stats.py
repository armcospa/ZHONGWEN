"""Tests for zhongwen_anki.analyze_stats (promoted from WIP)."""
import csv
from datetime import date

import pandas as pd
import pytest

from zhongwen_anki import analyze_stats
from zhongwen_anki import export_stats


COLUMNS = [
    "review_datetime", "deck", "current_filtered_deck", "note_id", "card_id", "word",
    "card_type", "tags", "note_guid", "ease", "ease_label", "is_user_answer", "is_correct",
    "interval", "last_interval", "ease_factor_percent", "time_seconds", "review_type",
]


def _write_csv(path, rows, columns=COLUMNS):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def _row(day, word, card_type, ease_label, is_correct, last_interval=5,
         review_type="review", deck="Chino - HSK1 (HSK 3.0)", time_seconds=3.0):
    ease = {"Again": 1, "Hard": 2, "Good": 3, "Easy": 4}[ease_label]
    is_user_answer = ease >= 1 and review_type not in ("manual", "rescheduled")
    return [
        f"2026-08-{day:02d} 09:00:00", deck, "", 1, 1, word, card_type,
        "HSK1", "GUID1", ease, ease_label, is_user_answer, is_correct, 10, last_interval, 250.0,
        time_seconds, review_type,
    ]


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "reviews.csv"
    rows = []
    # 你 is easy (mostly correct) on H2M.
    for day in range(1, 6):
        rows.append(_row(day, "你", "H2M", "Good", 1, last_interval=day))
    # 好 is hard (mostly wrong) on H2P -- a leech candidate.
    for day in range(1, 6):
        rows.append(_row(day, "好", "H2P", "Again", 0, last_interval=day))
    # A second HSK level, so the level breakdown has more than one row.
    rows.append(_row(3, "了", "H2M", "Good", 1, deck="Chino - HSK2 (HSK 3.0)"))
    _write_csv(path, rows)
    return path


# --- Loading ---


def test_load_derives_level_from_deck_name(sample_csv):
    df, cards = analyze_stats.load(sample_csv)
    assert set(df["level"]) == {"HSK1", "HSK2"}
    assert cards is None


def test_load_with_cards_csv(sample_csv, tmp_path):
    cards_path = tmp_path / "cards.csv"
    cards_path.write_text("card_id,word\n1,你\n", encoding="utf-8")
    df, cards = analyze_stats.load(sample_csv, cards_path)
    assert cards is not None
    assert len(cards) == 1


def test_load_fills_missing_card_type_for_old_exports(tmp_path):
    old_columns = [c for c in COLUMNS if c != "card_type"]
    path = tmp_path / "reviews.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(old_columns)
        writer.writerow(["2026-08-01 09:00:00", "Chino - HSK1 (HSK 3.0)", "", 1, 1, "你",
                          "HSK1", "GUID1", 3, "Good", 1, 10, 5, 250.0, 3.0, "review"])
    df, _ = analyze_stats.load(path)
    assert df["card_type"].tolist() == ["Desconocido"]


def test_load_maps_legacy_card_type_names_to_codes(tmp_path):
    path = tmp_path / "old.csv"
    _write_csv(path, [_row(1, "你", "Escribir Hanzi", "Good", 1),
                      _row(1, "好", "Significado -> Pinyin", "Again", 0)])
    df, _ = analyze_stats.load(path)
    assert list(df["card_type"]) == ["PM2H", "M2P"]


# --- Overview ---


def test_overview_counts_reviews_and_accuracy(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    ov = analyze_stats.overview(df)
    assert ov["total_reviews"] == 11
    assert ov["unique_words"] == 3
    assert ov["overall_accuracy"] == pytest.approx(6 / 11)


def test_overview_on_empty_dataframe(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    empty = df.iloc[0:0]
    assert analyze_stats.overview(empty) == {"total_reviews": 0}


def test_overview_calculates_streaks(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    # Use today=Aug 5 so the streak is alive
    ov = analyze_stats.overview(df, today=date(2026, 8, 5))
    # Reviews on Aug 1-5, so current streak = 5 and longest = 5
    assert ov["current_streak"] == 5
    assert ov["longest_streak"] == 5


def test_overview_includes_button_counts(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    ov = analyze_stats.overview(df)
    assert ov["total_good"] == 6
    assert ov["total_again"] == 5


# --- Accuracy metrics ---


def test_accuracy_by_card_type_flags_the_weaker_skill(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.accuracy_by(df, "card_type")
    worst = g.iloc[0]
    assert worst["card_type"] == "H2P"
    assert worst["accuracy"] == pytest.approx(0.0)
    best = g[g["card_type"] == "H2M"].iloc[0]
    assert best["accuracy"] == pytest.approx(1.0)


def test_accuracy_by_weekday(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.accuracy_by_weekday(df)
    assert not g.empty
    assert "weekday" in g.columns
    assert "accuracy" in g.columns


def test_accuracy_by_hour(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.accuracy_by_hour(df)
    assert not g.empty
    assert "hour" in g.columns


# --- Retention ---


def test_retention_by_interval_buckets_positive_review_intervals(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.retention_by_interval(df)
    assert g["reviews"].sum() == 11
    assert set(g["bucket"].astype(str)) <= {"1d", "2-3d", "4-7d", "8-30d", ">30d"}


def test_retention_by_interval_ignores_non_review_types(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    df = pd.concat([df, pd.DataFrame([{
        **df.iloc[0].to_dict(), "review_type": "learning", "last_interval": -600,
    }])], ignore_index=True)
    g = analyze_stats.retention_by_interval(df)
    assert g["reviews"].sum() == 11


# --- Daily trend ---


def test_daily_trend_has_one_row_per_calendar_day(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    daily = analyze_stats.daily_trend(df)
    assert len(daily) == 5  # Aug 1-5
    assert daily["reviews"].sum() == 11
    assert "accuracy_7d" in daily.columns


# --- Deep failure analysis ---


def test_hardest_words_surfaces_the_leech(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    hard = analyze_stats.hardest_words(df, min_reviews=3)
    assert hard.iloc[0]["word"] == "好"
    assert hard.iloc[0]["agains"] == 5


def test_hardest_words_excludes_low_review_count(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    hard = analyze_stats.hardest_words(df, min_reviews=3)
    assert "了" not in hard["word"].tolist()


def test_most_lapsed_words(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    lapsed = analyze_stats.most_lapsed_words(df, min_lapses=2)
    assert not lapsed.empty
    assert lapsed.iloc[0]["word"] == "好"
    assert lapsed.iloc[0]["agains"] == 5


def test_mastery_curve(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    mastery = analyze_stats.mastery_curve(df, consecutive_correct=5)
    assert not mastery.empty
    assert "mastered" in mastery.columns
    # 你 has 5 consecutive correct on H2M
    mastered = mastery[mastery["word"] == "你"]
    assert any(mastered["mastered"])


def test_mastery_curve_empty():
    empty = pd.DataFrame(columns=["word", "card_type", "is_correct", "review_datetime"])
    mastery = analyze_stats.mastery_curve(empty)
    assert mastery.empty


def test_lapse_history(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    lapses = analyze_stats.lapse_history(df)
    assert not lapses.empty
    assert lapses["word"].tolist().count("好") == 5
    assert "lapse_number" in lapses.columns


def test_words_needing_attention(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    attn = analyze_stats.words_needing_attention(df, min_reviews=3)
    # 好 should be flagged (0% accuracy, 5 lapses)
    assert not attn.empty
    assert "好" in attn["word"].tolist()


# --- Linguistic analysis ---


def test_tone_analysis_without_pinyin(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    tone = analyze_stats.tone_analysis(df)
    assert tone.empty  # No pinyin column in sample CSV


def test_tone_analysis_with_pinyin(tmp_path):
    path = tmp_path / "reviews.csv"
    vocab_columns = COLUMNS + ["pinyin", "meaning", "meaning_es", "vocab_level",
                                "traditional", "sentence", "sentence_meaning", "synonyms"]

    def vrow(day, word, pinyin, meaning_es, is_correct, ease_label="Again"):
        ease = 1 if ease_label == "Again" else 3
        return [f"2026-08-{day:02d} 09:00:00", "Chino - HSK1", "", 1, 1, word, "H2P", "HSK1",
                "GUID1", ease, ease_label, True, is_correct, 10, 5, 250.0, 3.0, "review",
                pinyin, "x", meaning_es, "HSK1", "", "", "", ""]

    rows = [vrow(d, "好", "hao3", "bueno", 0) for d in range(1, 6)]
    rows.append(vrow(6, "你", "ni3", "tú", 1, ease_label="Good"))
    _write_csv(path, rows, vocab_columns)
    df, _ = analyze_stats.load(path)
    tone = analyze_stats.tone_analysis(df)
    assert not tone.empty
    assert "tone_pattern" in tone.columns


def test_character_difficulty(tmp_path):
    path = tmp_path / "reviews.csv"
    rows = []
    for d in range(1, 6):
        rows.append([f"2026-08-0{d} 09:00:00", "HSK1", "", 1, 1, "你好", "M2H", "HSK1", "GUID1",
                     1, "Again", True, 0, 10, 5, 250.0, 3.0, "review"])
        rows.append([f"2026-08-0{d} 10:00:00", "HSK1", "", 1, 1, "世界", "M2H", "HSK1", "GUID2",
                     3, "Good", True, 1, 10, 5, 250.0, 3.0, "review"])
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    char_diff = analyze_stats.character_difficulty(df)
    assert not char_diff.empty
    assert "char" in char_diff.columns
    assert "你" in char_diff["char"].tolist()


def test_response_time_analysis(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.response_time_analysis(df)
    assert not g.empty
    assert "avg_time_correct" in g.columns
    assert "avg_time_incorrect" in g.columns


# --- Recommendations ---


def test_recommendations_empty_data(tmp_path):
    path = tmp_path / "empty.csv"
    _write_csv(path, [])
    df, _ = analyze_stats.load(path)
    recs = analyze_stats.generate_recommendations(df)
    assert len(recs) == 1
    assert "aún no hay datos" in recs[0]["message"].lower()


def test_recommendations_low_accuracy(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    recs = analyze_stats.generate_recommendations(df)
    # With ~55% accuracy, should have a low accuracy alert
    alert_recs = [r for r in recs if r["type"] == "alert"]
    assert len(alert_recs) > 0


def test_recommendations_weak_skills(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    recs = analyze_stats.generate_recommendations(df)
    # H2P is 0% accuracy, should be flagged as weak
    warning_recs = [r for r in recs if r["type"] == "warning"]
    assert len(warning_recs) > 0


# --- Report generation ---


def test_build_report_html_on_empty_data_is_friendly(tmp_path):
    path = tmp_path / "reviews.csv"
    _write_csv(path, [])
    df, _ = analyze_stats.load(path)
    report = analyze_stats.build_report_html(df)
    assert "Todavía no hay repasos" in report


def test_build_report_html_embeds_charts_and_hard_words(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "data:image/png;base64," in report
    assert "好" in report
    assert "Precisión por nivel" in report  # two levels present


def test_build_report_html_includes_recommendations(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "Recomendaciones personalizadas" in report


def test_build_report_html_includes_mastery(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "Curva de dominio" in report


def test_build_report_html_includes_needing_attention(sample_csv):
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "necesitan atención" in report or "necesitan atención" in report.lower()


# --- CLI ---


def test_main_writes_report_file(tmp_path, monkeypatch, sample_csv):
    output = tmp_path / "report.html"
    monkeypatch.setattr(
        "sys.argv",
        ["zhongwen-anki-analyze-stats", "-i", str(sample_csv), "-o", str(output)],
    )
    analyze_stats.main()
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Informe de aprendizaje" in content


def test_main_errors_when_input_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nope.csv"
    monkeypatch.setattr("sys.argv", ["zhongwen-anki-analyze-stats", "-i", str(missing)])
    with pytest.raises(SystemExit):
        analyze_stats.main()


# --- Helpers ---


def test_max_consecutive():
    assert analyze_stats._max_consecutive(pd.Series([True, True, False, True])) == 2
    assert analyze_stats._max_consecutive(pd.Series([False, False])) == 0
    assert analyze_stats._max_consecutive(pd.Series([True, True, True])) == 3


def test_level_sort_key():
    assert analyze_stats._level_sort_key("HSK1") < analyze_stats._level_sort_key("HSK2")
    assert analyze_stats._level_sort_key("Sin nivel") == 999


# --- Tone analysis with accented pinyin (pinyin_to_numbered) ---


def test_tone_analysis_with_accented_pinyin(tmp_path):
    """Tone analysis should work with accented pinyin via pinyin_to_numbered()."""
    path = tmp_path / "reviews.csv"
    vocab_columns = COLUMNS + ["pinyin", "meaning", "meaning_es", "vocab_level",
                                "traditional", "sentence", "sentence_meaning", "synonyms"]
    rows = []
    for d in range(1, 6):
        # Accented pinyin: àihào (ai4hao4 -> tones 4-4)
        rows.append([f"2026-08-0{d} 09:00:00", "Chino - HSK1", "", 1, 1, "爱好", "H2P", "HSK1",
                     "GUID_TONE1", 3, "Good", 1, 1, 10, 5, 250.0, 3.0, "review",
                     "àihào", "hobby", "hobby", "HSK1", "愛好", "", "", ""])
        # Accented pinyin: nǐhǎo (ni3hao3 -> tones 3-3)
        rows.append([f"2026-08-0{d} 10:00:00", "Chino - HSK1", "", 2, 1, "你好", "H2P", "HSK1",
                     "GUID_TONE2", 1, "Again", 1, 0, 10, 5, 250.0, 3.0, "review",
                     "nǐhǎo", "hello", "hola", "HSK1", "你", "", "", ""])
    _write_csv(path, rows, vocab_columns)
    df, _ = analyze_stats.load(path)
    tone = analyze_stats.tone_analysis(df)
    assert not tone.empty
    assert "tone_pattern" in tone.columns
    # Should have patterns "4-4" and "3-3"
    assert "4-4" in tone["tone_pattern"].tolist() or "3-3" in tone["tone_pattern"].tolist()


# --- Mastery curve: position not consecutive_correct ---


def test_mastery_curve_reports_position():
    """mastery_curve should report the position (review number) where mastery was reached,
    not the consecutive_correct count."""
    df = pd.DataFrame([
        {"review_datetime": pd.Timestamp(f"2026-08-{d:02d}"), "note_id": 1, "card_type": "H2M",
         "word": "你", "is_correct": correct, "review_type": "review"}
        for d, correct in enumerate([False, True, True, True, True, True], 1)
    ])
    mastery = analyze_stats.mastery_curve(df, mastery_streak=4)
    assert len(mastery) == 1
    # Position where 4 consecutive correct was reached: reviews 2,3,4,5 -> position=5
    assert mastery["reviews_to_mastery"].iloc[0] == 5


# --- Streak calculation with --today parameter ---


def test_streak_with_today_parameter():
    """Streak calculation should use --today reference date."""
    df = pd.DataFrame([
        {"review_datetime": pd.Timestamp(f"2026-08-{d:02d}")}
        for d in range(1, 6)  # Aug 1-5
    ])
    from datetime import date
    # Reference date = Aug 5, streak should be alive
    result = analyze_stats._calculate_streaks(df, today=date(2026, 8, 5))
    assert result["alive"] is True
    assert result["current"] == 5

    # Reference date = Aug 10, streak should be broken
    result = analyze_stats._calculate_streaks(df, today=date(2026, 8, 10))
    assert result["alive"] is False
    assert "last_ended" in result


# --- Badge HTML NOT escaped ---


def test_badge_html_not_escaped_in_table(sample_csv):
    """Badge HTML in attention table should NOT be escaped."""
    df, _ = analyze_stats.load(sample_csv)
    # Force words needing attention by lowering threshold
    attn = analyze_stats.words_needing_attention(df, min_reviews=1)
    if attn.empty:
        pytest.skip("No words needing attention in sample data")
    table_html = analyze_stats._table_html(attn, {
        "priority": ("Prioridad", lambda v: f'<span class="badge badge-{v}">{v}</span>', True),
    })
    # Badges should NOT be HTML-escaped, so raw <span should be present
    assert "&" + "lt;span" not in table_html  # escaped form should NOT appear
    assert '<span class="badge' in table_html  # raw HTML should be present


# --- Grouping by note_id (not word) ---


def test_hardest_words_groups_by_note_id(tmp_path):
    """hardest_words should group by note_id, not word."""
    path = tmp_path / "reviews.csv"
    rows = [
        # Same note_id, different words (should be grouped)
        ["2026-08-01 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         1, "Again", 1, 0, 10, 5, 250.0, 3.0, "review"],
        ["2026-08-02 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         1, "Again", 1, 0, 10, 5, 250.0, 3.0, "review"],
        ["2026-08-03 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         1, "Again", 1, 0, 10, 5, 250.0, 3.0, "review"],
        # Different note_id, same word (should NOT be grouped)
        ["2026-08-01 09:00:00", "HSK1", "", 2, 1, "你", "H2P", "HSK1", "GUID2",
         3, "Good", 1, 1, 10, 5, 250.0, 3.0, "review"],
        ["2026-08-02 09:00:00", "HSK1", "", 2, 1, "你", "H2P", "HSK1", "GUID2",
         3, "Good", 1, 1, 10, 5, 250.0, 3.0, "review"],
        ["2026-08-03 09:00:00", "HSK1", "", 2, 1, "你", "H2P", "HSK1", "GUID2",
         3, "Good", 1, 1, 10, 5, 250.0, 3.0, "review"],
    ]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    hard = analyze_stats.hardest_words(df, min_reviews=3)
    # Should have 2 groups: note_id=1 (H2M) and note_id=2 (H2P)
    assert len(hard) == 2
    assert hard[hard["note_id"] == 1]["accuracy"].iloc[0] == pytest.approx(0.0)
    assert hard[hard["note_id"] == 2]["accuracy"].iloc[0] == pytest.approx(1.0)


# --- Non-user answers filtered out ---


def test_filter_user_answers_excludes_system_actions(tmp_path):
    """filter_user_answers should exclude type 4 and 5."""
    path = tmp_path / "reviews.csv"
    rows = [
        # Normal user answer
        ["2026-08-01 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         3, "Good", True, 1, 10, 5, 250.0, 3.0, "review"],
        # System action (manual)
        ["2026-08-02 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         3, "Good", False, 1, 10, 5, 250.0, 3.0, "manual"],
    ]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    filtered = analyze_stats.filter_user_answers(df)
    assert len(filtered) == 1
    assert filtered.iloc[0]["review_type"] == "review"


# --- "Toda la información" excluded from accuracy ---


def test_exclude_info_only_from_accuracy(tmp_path):
    """'Toda la información' card type should be excluded from accuracy."""
    path = tmp_path / "reviews.csv"
    rows = [
        ["2026-08-01 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         1, "Again", True, 0, 10, 5, 250.0, 3.0, "review"],
        ["2026-08-02 09:00:00", "HSK1", "", 1, 1, "你", "Toda la información", "HSK1", "GUID1",
         1, "Again", True, 0, 10, 5, 250.0, 3.0, "review"],
    ]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    accuracy_df = analyze_stats.exclude_info_only(df)
    assert len(accuracy_df) == 1
    assert accuracy_df.iloc[0]["card_type"] == "H2M"


# --- "Fallos (Again)" label ---


def test_fallos_again_label_in_report(sample_csv):
    """Report should use 'Fallos (Again)' label, not 'lapsos'."""
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "Fallos (Again)" in report
    assert "lapsos" not in report.lower() or "Fallos (Again)" in report


# --- --mastery-streak flag ---


def test_mastery_streak_flag(sample_csv):
    """mastery_curve should respect mastery_streak parameter."""
    df, _ = analyze_stats.load(sample_csv)
    # With streak=3
    m3 = analyze_stats.mastery_curve(df, mastery_streak=3)
    # With streak=5
    m5 = analyze_stats.mastery_curve(df, mastery_streak=5)
    mastered_3 = m3["mastered"].sum()
    mastered_5 = m5["mastered"].sum()
    # More (or equal) combos should be mastered with lower streak
    assert mastered_3 >= mastered_5


# --- Low ease (<=150%) detection, skip when FSRS present ---


def test_low_ease_detection_with_cards_df(tmp_path):
    """Recommendations should detect low ease hell, but skip when FSRS present."""
    path = tmp_path / "reviews.csv"
    _write_csv(path, [
        ["2026-08-01 09:00:00", "HSK1", "", 1, 1, "你", "H2M", "HSK1", "GUID1",
         3, "Good", True, 1, 10, 5, 150.0, 3.0, "review"],
    ])
    df, _ = analyze_stats.load(path)

    # Create cards_df with low ease but no FSRS
    cards_df = pd.DataFrame([
        {"ease_factor_percent": "140.0", "fsrs_stability": "", "fsrs_difficulty": ""}
        for _ in range(15)
    ])
    recs = analyze_stats.generate_recommendations(df, cards_df=cards_df)
    ease_hell_recs = [r for r in recs if "ease hell" in r.get("title", "").lower()]
    assert len(ease_hell_recs) > 0

    # Now with FSRS present - should skip
    cards_df_fsrs = pd.DataFrame([
        {"ease_factor_percent": "140.0", "fsrs_stability": "1.5", "fsrs_difficulty": "2.0"}
        for _ in range(15)
    ])
    recs = analyze_stats.generate_recommendations(df, cards_df=cards_df_fsrs)
    ease_hell_recs = [r for r in recs if "ease hell" in r.get("title", "").lower()]
    assert len(ease_hell_recs) == 0


# --- Hour chart produces matplotlib output ---


def test_hour_chart_produces_matplotlib_output(sample_csv):
    """chart_hour should produce a base64-encoded PNG."""
    df, _ = analyze_stats.load(sample_csv)
    hour_df = analyze_stats.accuracy_by_hour(df)
    chart_uri = analyze_stats.chart_hour(hour_df)
    assert chart_uri.startswith("data:image/png;base64,")


# --- Response time analysis with groupby+unstack ---


def test_response_time_analysis_uses_unstack(sample_csv):
    """response_time_analysis should produce correct columns."""
    df, _ = analyze_stats.load(sample_csv)
    g = analyze_stats.response_time_analysis(df)
    assert not g.empty
    assert "avg_time_correct" in g.columns
    assert "avg_time_incorrect" in g.columns
    assert "overall_avg" in g.columns
    assert "reviews" in g.columns


# --- Character difficulty with explode ---


def test_character_difficulty_uses_explode(tmp_path):
    """character_difficulty should use explode for per-character analysis."""
    path = tmp_path / "reviews.csv"
    rows = []
    for d in range(1, 6):
        rows.append([f"2026-08-0{d} 09:00:00", "HSK1", "", 1, 1, "你好", "M2H", "HSK1", "GUID1",
                     1, "Again", True, 0, 10, 5, 250.0, 3.0, "review"])
        rows.append([f"2026-08-0{d} 10:00:00", "HSK1", "", 1, 1, "世界", "M2H", "HSK1", "GUID2",
                     3, "Good", True, 1, 10, 5, 250.0, 3.0, "review"])
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    char_diff = analyze_stats.character_difficulty(df)
    assert not char_diff.empty
    assert "char" in char_diff.columns
    # Should have individual characters: 你, 好, 世, 界
    assert "你" in char_diff["char"].tolist()
    assert "好" in char_diff["char"].tolist()


# --- Retention interval buckets with labels and sample sizes ---


def test_retention_buckets_have_labels_and_sample_sizes(sample_csv):
    """retention_by_interval should produce labeled buckets with sample sizes."""
    df, _ = analyze_stats.load(sample_csv)
    retention = analyze_stats.retention_by_interval(df)
    assert not retention.empty
    assert "bucket" in retention.columns
    assert "reviews" in retention.columns
    assert "reliable" in retention.columns
    # Labels should be proper bucket names
    valid_labels = {"1d", "2-3d", "4-7d", "8-30d", ">30d"}
    for label in retention["bucket"].astype(str).tolist():
        assert label in valid_labels, f"Invalid bucket label: {label}"


# --- Generate recommendations works on df.copy() ---


def test_generate_recommendations_does_not_modify_original(sample_csv):
    """generate_recommendations should work on copies, not modify original df."""
    df, _ = analyze_stats.load(sample_csv)
    original_len = len(df)
    original_cols = list(df.columns)
    recs = analyze_stats.generate_recommendations(df)
    assert len(recs) > 0
    # Original df should be unchanged
    assert len(df) == original_len
    assert list(df.columns) == original_cols


# --- NO "Chart.js CDN" or "定向" strings ---


def test_no_chart_js_cdn_in_report(sample_csv):
    """Report should NOT contain Chart.js CDN references."""
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df)
    assert "Chart.js" not in report
    assert "cdn" not in report.lower() or "Chart.js" not in report


def test_no_dingxiang_string_in_report(sample_csv):
    """Report should NOT contain '定向' string."""
    df, _ = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df)
    assert "定向" not in report


# --- End-to-end: synthetic collection -> export -> analyze -> verify HTML ---


def test_end_to_end_synthetic_collection(tmp_path):
    """Create a synthetic collection, export CSV, analyze, and verify HTML output."""
    import sqlite3 as sqlite3_mod

    # Step 1: Create synthetic in-memory SQLite collection
    collection = tmp_path / "collection.anki2"
    con = sqlite3_mod.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")  # crt in seconds since epoch
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (HSK 3.0)')")
    con.execute("INSERT INTO decks VALUES (2, 'Chino - HSK2 (HSK 3.0)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', ' HSK1 ', 'GUID_E2E_1')")
    con.execute("INSERT INTO notes VALUES (101, '世界\x1fworld', ' HSK2 ', 'GUID_E2E_2')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER, "
        "odue INTEGER, reps INTEGER, data TEXT)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0, 0, 10, '')")
    con.execute("INSERT INTO cards VALUES (201, 101, 2, 0, 2, 2528, 7, 2600, 1, 2, 0, 0, 5, '')")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # Multiple reviews over several days
    for day in range(1, 8):
        epoch = 1788336000000 + day * 86400000  # Starting 2026-08-01
        con.execute("INSERT INTO revlog VALUES (?, 200, 3, 4, 1, 2500, 5000, 1)", (epoch,))
        con.execute("INSERT INTO revlog VALUES (?, 201, 1, -600, 4, 2600, 3000, 1)", (epoch + 1000,))
    con.commit()
    con.close()

    # Step 2: Export reviews CSV
    reviews_csv = tmp_path / "reviews.csv"
    cards_csv = tmp_path / "cards.csv"
    num_reviews = export_stats.export_reviews(collection, reviews_csv)
    assert num_reviews == 14  # 7 days * 2 cards
    export_stats.export_card_snapshot(collection, cards_csv)

    # Step 3: Load and analyze
    df, cards = analyze_stats.load(reviews_csv, cards_csv)
    assert len(df) == 14
    assert cards is not None

    # Step 4: Build report
    from datetime import date as dt_date
    report = analyze_stats.build_report_html(df, cards, today=dt_date(2026, 8, 10))

    # Step 5: Verify HTML contains expected elements
    assert "<!doctype html>" in report.lower()
    assert "Informe de aprendizaje" in report
    assert "data:image/png;base64," in report
    assert "Precisión por tipo de tarjeta" in report
    assert "Recomendaciones personalizadas" in report or "Todavía no hay" not in report
    assert "Fallos (Again)" in report
    assert "Chart.js" not in report
    assert "定向" not in report
    assert "lapsos" not in report or "Fallos (Again)" in report


# --- Plan v3, C.3: regression tests for report changes --------------------


def test_broken_streak_current_zero(tmp_path):
    """_calculate_streaks reports current=0 for a broken streak; the HTML
    shows the 'Racha máxima' tile and '0 (última sesión: ...)'."""
    path = tmp_path / "reviews.csv"
    rows = [_row(day, "你", "H2M", "Good", 1) for day in range(1, 6)]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    streaks = analyze_stats._calculate_streaks(df, today=date(2026, 8, 20))
    assert streaks["current"] == 0
    assert streaks["alive"] is False
    report = analyze_stats.build_report_html(df, today=date(2026, 8, 20))
    assert "Racha máxima" in report
    assert "0 (última sesión:" in report


def test_report_learning_only_history(tmp_path):
    """A history with only learning steps shows 'Aún no hay repasos programados'
    and never leaks the {mastery_streak} placeholder or *review* asterisks."""
    path = tmp_path / "reviews.csv"
    rows = [_row(day, "你", "H2M", "Good", 1, review_type="learning") for day in range(1, 6)]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    report = analyze_stats.build_report_html(df)
    assert "Aún no hay repasos programados" in report
    assert "{mastery_streak}" not in report
    assert "*review*" not in report


def test_insufficient_data_first_rec_is_warning(tmp_path):
    """With few data, the first rec-box is 'Datos aún escasos' and no
    recommendation keeps a high priority."""
    path = tmp_path / "reviews.csv"
    rows = [_row(day, "好", "H2P", "Again", 0) for day in range(1, 4)]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    recs = analyze_stats.generate_recommendations(df, today=date(2026, 8, 20))
    assert recs[0]["title"] == "Datos aún escasos"
    assert all(r.get("priority", "low") != "high" for r in recs)
    report = analyze_stats.build_report_html(df, today=date(2026, 8, 20))
    first_box = report[report.find('class="rec-box'):]
    title_start = first_box.find('class="rec-title"')
    title_end = first_box.find("</div>", title_start)
    assert "Datos aún escasos" in first_box[title_start:title_end]


def test_info_card_excluded_from_accuracy_tile(tmp_path):
    """'Toda la información' rows count in the volume tile but not in the
    accuracy tile: 20 repasos and 50 %."""
    path = tmp_path / "reviews.csv"
    rows = []
    for day in range(1, 6):
        rows.append(_row(day, "你好", "Toda la información", "Good", 1, last_interval=5))
        rows.append(_row(day, "你好", "Toda la información", "Good", 1, last_interval=5))
        rows.append(_row(day, "世界", "H2M", "Good", 1, last_interval=5))
        rows.append(_row(day, "世界", "H2M", "Again", 0, last_interval=5))
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    report = analyze_stats.build_report_html(df)
    assert '<div class="value">20</div><div class="label">Repasos totales</div>' in report
    assert '<div class="value">50%</div><div class="label">Precisión global</div>' in report


def test_relearning_only_affects_matching_card_type(tmp_path):
    """Cross-check with the card snapshot: only the (note, M2P) card in
    relearning gets 'en relearning', not the H2M card of the same note."""
    path = tmp_path / "reviews.csv"
    rows = []
    for day in range(1, 6):
        # H2M: 2 correct + 3 Again (flagged for low accuracy, but NOT relearning)
        h2m_ok = day <= 2
        rows.append([f"2026-08-{day:02d} 09:00:00", "Chino - HSK1", "", 10, 1, "你好", "H2M",
                     "HSK1", "G1", 3 if h2m_ok else 1, "Good" if h2m_ok else "Again", True,
                     int(h2m_ok), 10, 5, 250.0, 3.0, "review"])
        # M2P: all Again (flagged, and relearning in the snapshot)
        rows.append([f"2026-08-{day:02d} 10:00:00", "Chino - HSK1", "", 10, 2, "你好", "M2P",
                     "HSK1", "G1", 1, "Again", True, 0, 10, 5, 250.0, 3.0, "review"])
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    cards = pd.DataFrame({
        "note_id": [10, 10],
        "card_id": [1, 2],
        "card_type": ["H2M", "M2P"],
        "queue": [2, 3],
        "type": [2, 3],
        "ease_factor_percent": [250, 250],
    })
    attn = analyze_stats.words_needing_attention(df, cards, min_reviews=5)
    # Both (note 10, H2M) and (note 10, M2P) are flagged for low accuracy.
    assert len(attn) == 2
    with_relearning = attn[attn["reasons"].str.contains("en relearning")]
    without_relearning = attn[~attn["reasons"].str.contains("en relearning")]
    # Only the M2P card (type 3 in the snapshot) carries the relearning reason.
    assert len(with_relearning) == 1
    assert len(without_relearning) == 1
    assert with_relearning.iloc[0]["agains"] == 5
    assert with_relearning.iloc[0]["priority"] == "alta"
    assert without_relearning.iloc[0]["agains"] == 3


def test_priority_badges_in_html_and_css(tmp_path):
    """The attention table renders priority badges and _PAGE_CSS defines them."""
    path = tmp_path / "reviews.csv"
    rows = [_row(day, "好", "H2P", "Again", 0) for day in range(1, 6)]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    report = analyze_stats.build_report_html(df)
    assert "badge-alta" in report or "badge-media" in report
    assert ".badge-alta" in analyze_stats._PAGE_CSS
    assert ".badge-media" in analyze_stats._PAGE_CSS


def test_legacy_csv_without_new_columns(tmp_path):
    """Legacy CSV (HEAD header: no review_id/is_user_answer/note_guid) with
    manual and ease=0 rows: manual rows are excluded and nothing crashes."""
    path = tmp_path / "reviews.csv"
    legacy_cols = [
        "review_datetime", "deck", "current_filtered_deck", "note_id", "card_id", "word",
        "card_type", "tags", "ease", "ease_label", "is_correct", "interval",
        "last_interval", "ease_factor_percent", "time_seconds", "review_type",
    ]
    rows = []
    for day in range(1, 7):
        rows.append([f"2026-08-{day:02d} 09:00:00", "Chino - HSK1", "", 1, 1, "你", "H2M",
                     "HSK1", 3, "Good", 1, 10, 5, 250.0, 3.0, "review"])
    rows.append(["2026-08-07 09:00:00", "Chino - HSK1", "", 1, 1, "你", "H2M", "HSK1",
                 0, "", 0, 10, 5, 0.0, 0.0, "manual"])
    rows.append(["2026-08-07 10:00:00", "Chino - HSK1", "", 1, 1, "你", "H2M", "HSK1",
                 0, "", 0, 10, 5, 0.0, 0.0, "rescheduled"])
    _write_csv(path, rows, legacy_cols)
    df, _ = analyze_stats.load(path)
    user = analyze_stats.filter_user_answers(df)
    assert len(user) == 6
    report = analyze_stats.build_report_html(df)
    assert '<div class="value">6</div><div class="label">Repasos totales</div>' in report


def test_chart_hard_words_title_uses_min_reviews(tmp_path, monkeypatch):
    """chart_hard_words must show the passed min_reviews in its title."""
    path = tmp_path / "reviews.csv"
    rows = [_row(day, "好", "H2P", "Again", 0) for day in range(1, 8)]
    _write_csv(path, rows)
    df, _ = analyze_stats.load(path)
    hard = analyze_stats.hardest_words(df, min_reviews=7)
    assert not hard.empty
    captured = {}

    def fake_fig_to_uri(fig):
        captured["fig"] = fig
        return "data:image/png;base64,FAKE"

    monkeypatch.setattr(analyze_stats, "_fig_to_data_uri", fake_fig_to_uri)
    analyze_stats.chart_hard_words(hard, min_reviews=7)
    assert "mín. 7 repasos" in captured["fig"].axes[0].get_title()


def test_report_shows_recent_lapses_table(sample_csv):
    """When there are lapses, the report renders the 'Últimos fallos' table."""
    df, cards = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, cards)
    assert "Últimos fallos" in report


def test_main_fails_when_cards_snapshot_is_missing(sample_csv, tmp_path, monkeypatch):
    missing = tmp_path / "missing.cards.csv"
    monkeypatch.setattr("sys.argv", [
        "zhongwen-anki-analyze-stats", "-i", str(sample_csv),
        "--cards", str(missing), "-o", str(tmp_path / "report.html"),
    ])
    with pytest.raises(SystemExit, match="missing.cards.csv not found"):
        analyze_stats.main()
    assert not (tmp_path / "report.html").exists()
