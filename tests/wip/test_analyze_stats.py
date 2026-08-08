import csv

import pandas as pd
import pytest

from zhongwen_anki.wip import analyze_stats

COLUMNS = [
    "review_datetime", "deck", "note_id", "card_id", "word", "card_type",
    "ease", "ease_label", "is_correct", "interval", "last_interval",
    "ease_factor_percent", "time_seconds", "review_type",
]


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def _row(day, word, card_type, ease_label, is_correct, last_interval=5,
         review_type="review", deck="Chino - HSK1 (HSK 3.0)", time_seconds=3.0):
    ease = {"Again": 1, "Hard": 2, "Good": 3, "Easy": 4}[ease_label]
    return [
        f"2026-08-{day:02d} 09:00:00", deck, 1, 1, word, card_type,
        ease, ease_label, is_correct, 10, last_interval, 250.0, time_seconds, review_type,
    ]


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "reviews.csv"
    rows = []
    # 你 is easy (mostly correct) on Hanzi -> Significado.
    for day in range(1, 6):
        rows.append(_row(day, "你", "Hanzi -> Significado", "Good", 1, last_interval=day))
    # 好 is hard (mostly wrong) on Escribir Pinyin -- a leech candidate.
    for day in range(1, 6):
        rows.append(_row(day, "好", "Escribir Pinyin", "Again", 0, last_interval=day))
    # A second HSK level, so the level breakdown has more than one row.
    rows.append(_row(3, "了", "Hanzi -> Significado", "Good", 1, deck="Chino - HSK2 (HSK 3.0)"))
    _write_csv(path, rows)
    return path


def test_load_derives_level_from_deck_name(sample_csv):
    df = analyze_stats.load(sample_csv)
    assert set(df["level"]) == {"HSK1", "HSK2"}


def test_load_fills_missing_card_type_for_old_exports(tmp_path):
    path = tmp_path / "reviews.csv"
    old_columns = [c for c in COLUMNS if c != "card_type"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(old_columns)
        writer.writerow(["2026-08-01 09:00:00", "Chino - HSK1 (HSK 3.0)", 1, 1, "你",
                          3, "Good", 1, 10, 5, 250.0, 3.0, "review"])
    df = analyze_stats.load(path)
    assert df["card_type"].tolist() == ["Desconocido"]


def test_overview_counts_reviews_and_accuracy(sample_csv):
    df = analyze_stats.load(sample_csv)
    ov = analyze_stats.overview(df)
    assert ov["total_reviews"] == 11
    assert ov["unique_words"] == 3
    assert ov["overall_accuracy"] == pytest.approx(6 / 11)


def test_overview_on_empty_dataframe(sample_csv):
    df = analyze_stats.load(sample_csv).iloc[0:0]
    assert analyze_stats.overview(df) == {"total_reviews": 0}


def test_accuracy_by_card_type_flags_the_weaker_skill(sample_csv):
    df = analyze_stats.load(sample_csv)
    g = analyze_stats.accuracy_by(df, "card_type")
    worst = g.iloc[0]
    assert worst["card_type"] == "Escribir Pinyin"
    assert worst["accuracy"] == pytest.approx(0.0)
    best = g[g["card_type"] == "Hanzi -> Significado"].iloc[0]
    assert best["accuracy"] == pytest.approx(1.0)


def test_hardest_words_surfaces_the_leech(sample_csv):
    df = analyze_stats.load(sample_csv)
    hard = analyze_stats.hardest_words(df, min_reviews=3)
    assert hard.iloc[0]["word"] == "好"
    assert hard.iloc[0]["lapses"] == 5


def test_hardest_words_excludes_low_review_count(sample_csv):
    df = analyze_stats.load(sample_csv)
    hard = analyze_stats.hardest_words(df, min_reviews=3)
    assert "了" not in hard["word"].tolist()


def test_retention_by_interval_buckets_positive_review_intervals(sample_csv):
    df = analyze_stats.load(sample_csv)
    g = analyze_stats.retention_by_interval(df)
    assert g["reviews"].sum() == 11  # all rows are review_type="review" with last_interval > 0
    assert set(g["bucket"].astype(str)) <= {"<1d", "1-3d", "3-7d", "7-30d", "30d+"}


def test_retention_by_interval_ignores_non_review_types(sample_csv):
    df = analyze_stats.load(sample_csv)
    df = pd.concat([df, pd.DataFrame([{
        **df.iloc[0].to_dict(), "review_type": "learning", "last_interval": -600,
    }])], ignore_index=True)
    g = analyze_stats.retention_by_interval(df)
    # the injected learning-step row must not appear in any bucket
    assert g["reviews"].sum() == 11


def test_daily_trend_has_one_row_per_calendar_day(sample_csv):
    df = analyze_stats.load(sample_csv)
    daily = analyze_stats.daily_trend(df)
    assert len(daily) == 5  # Aug 1-5
    assert daily["reviews"].sum() == 11


def test_build_report_html_on_empty_data_is_friendly(tmp_path):
    path = tmp_path / "reviews.csv"
    _write_csv(path, [])
    df = analyze_stats.load(path)
    report = analyze_stats.build_report_html(df)
    assert "Todavía no hay repasos" in report


def test_build_report_html_embeds_charts_and_hard_words_table(sample_csv):
    df = analyze_stats.load(sample_csv)
    report = analyze_stats.build_report_html(df, min_reviews=3)
    assert "data:image/png;base64," in report
    assert "好" in report
    assert "Precisión por nivel" in report  # two levels present


def test_main_writes_report_file(tmp_path, monkeypatch, sample_csv):
    output = tmp_path / "report.html"
    monkeypatch.setattr(
        "sys.argv",
        ["zhongwen-anki-analyze-stats", "-i", str(sample_csv), "-o", str(output)],
    )
    analyze_stats.main()
    assert output.exists()
    assert "Informe de aprendizaje" in output.read_text(encoding="utf-8")


def test_main_errors_when_input_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nope.csv"
    monkeypatch.setattr("sys.argv", ["zhongwen-anki-analyze-stats", "-i", str(missing)])
    with pytest.raises(SystemExit):
        analyze_stats.main()
