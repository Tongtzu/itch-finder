import json

from itch_finder.__main__ import main
from itch_finder.cluster import cluster
from itch_finder.models import Post
from itch_finder.offers import build_stack
from itch_finder.report import render
from itch_finder.signals import score_post


def test_render_includes_evidence_and_offer_table():
    posts = [score_post(Post(source="reddit", post_id=str(i), title=f"Invoice [{i}] is a nightmare",
                             body="would pay", url=f"https://x/{i}", comments=1, upvotes=1,
                             created_utc=0)) for i in range(3)]
    clusters = cluster(posts, top_n=2)
    stacks = {c.keyword: build_stack(c, "excel") for c in clusters}
    md = render("excel", "2026-11-02", 10, clusters, stacks, {"invoice": "Angle text"})
    assert "# Pain report: excel (2026-11-02)" in md
    assert "[Invoice (0) is a nightmare](https://x/0)" in md
    assert "| done-for-you | **Invoice Done-For-You Setup**" in md
    assert "Angle text" in md


def test_render_empty_clusters_suggests_next_step():
    md = render("excel", "2026-11-02", 0, [], {}, {})
    assert "No qualifying pain found" in md


def test_cli_sale_and_status_persist_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["launch", "Kit"]) == 0
    assert main(["sale", "Kit", "19"]) == 0
    ledger = json.loads((tmp_path / "itch_finder_ledger.json").read_text())
    assert ledger == {"sales": [{"offer": "Kit", "amount": 19.0}], "launched": ["Kit"]}
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "$381 to go" in out
    assert "WATCH  Kit" in out


def test_cli_rejects_bad_sale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["sale", "Kit", "-5"]) == 2
