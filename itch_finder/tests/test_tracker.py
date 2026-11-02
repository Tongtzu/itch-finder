import pytest

from itch_finder.tracker import (conversions, empty_ledger, progress, record_sale, replicate,
                                 verdicts)


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


def test_record_sale_keeps_source_when_given():
    updated = record_sale(empty_ledger(), "Kit", 19, source="reddit")
    assert updated["sales"][0] == {"offer": "Kit", "amount": 19.0, "source": "reddit"}


def test_conversions_join_sales_with_replies():
    ledger = record_sale(empty_ledger(), "Kit", 19, source="hn")
    ledger = record_sale(ledger, "Kit", 19, source="hn")
    ledger = record_sale(ledger, "DFY", 197)
    rows = conversions(ledger, {("Kit", "hn"): 8, ("Kit", "reddit"): 4})
    by_pair = {(r["offer"], r["source"]): r for r in rows}
    assert by_pair[("Kit", "hn")] == {"offer": "Kit", "source": "hn", "sales": 2,
                                      "revenue": 38.0, "replies": 8, "rate": 0.25}
    assert by_pair[("Kit", "reddit")]["rate"] == 0.0
    assert by_pair[("DFY", "unknown")]["rate"] is None
    assert rows[0]["offer"] == "DFY"


def test_replicate_picks_top_revenue_pair_or_none():
    assert replicate(conversions(empty_ledger(), {("Kit", "hn"): 3})) is None
    ledger = record_sale(empty_ledger(), "Kit", 19, source="hn")
    assert replicate(conversions(ledger, {}))["source"] == "hn"
