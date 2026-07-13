import sqlite3

from equities.eval.calibration import brier_by_band, calibration_inverted


def _seed(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE positions (confidence REAL, strategy TEXT, sector TEXT, "
        "exit_reason TEXT, realized_pnl REAL, status TEXT)"
    )
    con.executemany("INSERT INTO positions VALUES (?,?,?,?,?,'closed')", rows)
    con.commit(); con.close()


def test_inversion_detected(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [
        (0.85, "s", "", "time_stop", -5.0), (0.80, "s", "", "time_stop", -4.0),
        (0.90, "s", "", "stop_hit", -6.0),  # high band 0/3
        (0.50, "s", "", "target_hit", 2.0), (0.55, "s", "", "target_hit", 1.5),
        (0.52, "s", "", "target_hit", 1.0),  # low band 3/3
    ])
    assert calibration_inverted(db) is True
    briers = brier_by_band(db)
    assert briers["0.75-1.00"] > briers["0.00-0.60"]


def test_no_inversion_with_healthy_book(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [
        (0.85, "s", "", "target_hit", 5.0), (0.80, "s", "", "target_hit", 4.0),
        (0.90, "s", "", "target_hit", 6.0),
        (0.50, "s", "", "stop_hit", -2.0), (0.55, "s", "", "stop_hit", -1.5),
        (0.52, "s", "", "target_hit", 1.0),
    ])
    assert calibration_inverted(db) is False


def test_small_sample_never_inverted(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [(0.85, "s", "", "time_stop", -5.0)])
    assert calibration_inverted(db) is False
