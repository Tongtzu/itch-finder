import json
import time

import itch_finder.__main__ as cli
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


def _fake_posts(*_args, **_kwargs):
    return [Post(source="stackexchange", post_id="7", title="Is there a tool to fix VBA? Frustrated",
                 body="My macro keeps crashing every day", url="https://x/7", comments=2,
                 upvotes=1, created_utc=time.time() - 60)]


def test_cli_intercept_drafts_replied_and_status(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_gather", _fake_posts)
    assert main(["intercept", "--niche", "excel", "--no-hn", "--se-sites", "superuser"]) == 0
    queue = json.loads((tmp_path / "itch_queue.json").read_text())
    assert queue["items"][0]["id"] == "stackexchange:7"

    assert main(["drafts", "--offer", "VBA Fix Kit"]) == 0
    draft_files = list((tmp_path / "itch_drafts").glob("*.md"))
    assert len(draft_files) == 1
    assert "Disclosure: I made VBA Fix Kit" in draft_files[0].read_text(encoding="utf-8")

    assert main(["replied", "stackexchange:7", "--offer", "VBA Fix Kit"]) == 0
    assert main(["sale", "VBA Fix Kit", "19", "--source", "stackexchange"]) == 0
    out = capsys.readouterr().out
    assert "VBA Fix Kit / stackexchange" in out
    assert "Replicate: VBA Fix Kit via stackexchange" in out


def test_cli_drafts_with_empty_queue(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["drafts"]) == 0
    assert "Nothing new" in capsys.readouterr().out


def test_cli_mine_with_brand_writes_listings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    posts = [Post(source="hn", post_id=str(i), title=f"VBA macro frustrating {i}", body="would pay",
                  url=f"https://x/{i}", comments=0, upvotes=0, created_utc=0) for i in range(3)]
    monkeypatch.setattr(cli, "_gather", lambda *a, **k: posts)
    assert main(["mine", "--niche", "excel", "--brand", "Sheet Rescue", "--min-score", "0"]) == 0
    listings = list((tmp_path / "itch_listings").glob("*.md"))
    assert len(listings) == 1
    assert "*by Sheet Rescue*" in listings[0].read_text(encoding="utf-8")
