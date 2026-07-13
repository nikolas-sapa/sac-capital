"""Attribution engine: bucket math + graded-lesson selection."""
import sqlite3

from equities.analysis.attribution import (
    attribute,
    calibration_size_cap,
    confidence_band_stats,
    graded_lessons,
)


def _seed(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE positions (confidence REAL, strategy TEXT, sector TEXT, "
        "exit_reason TEXT, realized_pnl REAL, status TEXT)"
    )
    con.executemany(
        "INSERT INTO positions VALUES (?,?,?,?,?,?)",
        [(*r, "closed") for r in rows],
    )
    con.commit()
    con.close()


def test_high_confidence_bucket_flagged_as_underperforming(tmp_path):
    db = str(tmp_path / "equity.db")
    # High-confidence trades all lose; low-confidence all win (the inverted
    # calibration seen in the live book).
    _seed(db, [
        (0.85, "equity_analyst", "Tech", "time_stop", -5.0),
        (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
        (0.90, "equity_analyst", "Tech", "stop_loss", -6.0),
        (0.50, "research_static", "Tech", "take_profit", 2.0),
        (0.55, "research_static", "Tech", "take_profit", 1.5),
        (0.50, "research_static", "Tech", "take_profit", 1.0),
    ])
    report = attribute(db)
    assert report.closed_trades == 6

    hi = next(b for b in report.buckets if b.dimension == "confidence" and b.label.startswith("0.75"))
    assert hi.n == 3 and hi.wins == 0
    assert hi.avg_pnl < 0

    lessons = graded_lessons(report, min_n=3)
    text = " ".join(lessons)
    assert "confidence=0.75-1.00" in text and "underperforms" in text
    # Winning low-confidence strategy should read as outperforming.
    assert "research_static" in text and "outperforms" in text


def test_small_sample_yields_no_lessons(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [(0.8, "equity_analyst", "Tech", "time_stop", -1.0)])
    assert graded_lessons(attribute(db), min_n=3) == []


def test_missing_table_is_empty_not_error(tmp_path):
    db = str(tmp_path / "empty.db")
    sqlite3.connect(db).close()
    report = attribute(db)
    assert report.closed_trades == 0 and report.buckets == []


def test_confidence_band_stats_keys_by_band(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [
        (0.85, "equity_analyst", "Tech", "time_stop", -5.0),
        (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
        (0.90, "equity_analyst", "Tech", "stop_hit", -6.0),
        (0.50, "research_static", "Tech", "target_hit", 2.0),
    ])
    stats = confidence_band_stats(db)
    assert stats["0.75-1.00"].n == 3
    assert stats["0.75-1.00"].avg_pnl < 0
    assert stats["0.00-0.60"].n == 1


def test_calibration_size_cap_fires_on_inverted_band(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [
        (0.85, "equity_analyst", "Tech", "time_stop", -5.0),
        (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
        (0.90, "equity_analyst", "Tech", "stop_hit", -6.0),
    ])
    # 0.82 falls in the 0.75-1.00 band: n=3, negative avg -> capped
    assert calibration_size_cap(0.82, db) == 0.01
    # 0.50 band has no data -> no cap
    assert calibration_size_cap(0.50, db) is None


def test_calibration_size_cap_respects_min_n(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [(0.85, "equity_analyst", "Tech", "time_stop", -5.0)])
    assert calibration_size_cap(0.85, db, min_n=3) is None
