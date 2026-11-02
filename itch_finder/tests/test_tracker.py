import pytest

from itch_finder.tracker import empty_ledger, record_sale, progress, verdicts


def test_record_sale_returns_new_ledger():
    ledger = empty_ledger()
    updated = record_sale(ledger, "Invoice Fix Kit", 19)
    assert ledger["sales"] == []
    assert updated["sales"][0] == {"offer": "Invoice Fix Kit", "amount": 19.0}


def test_record_sale_rejects_bad_amount():
    with pytest.raises(ValueError):
        record_sale(empty_ledger(), "x", 0)
    with pytest.raises(ValueError):
        record_sale(empty_ledger(), "", 10)


def test_progress_tracks_both_goals():
    ledger = empty_ledger()
    for _ in range(3):
        ledger = record_sale(ledger, "DFY setup", 150)
    p = progress(ledger)
    assert p["revenue"] == 450
    assert p["sprint_done"] is True
    assert p["engine_pct"] == pytest.approx(4.5)


def test_verdicts_scale_watch_kill():
    ledger = empty_ledger()
    for _ in range(3):
        ledger = record_sale(ledger, "A", 19)
    ledger = record_sale(ledger, "B", 19)
    ledger = {**ledger, "launched": ["A", "B", "C"]}
    v = verdicts(ledger, min_sales=3)
    assert v == {"A": "SCALE", "B": "WATCH", "C": "KILL"}
