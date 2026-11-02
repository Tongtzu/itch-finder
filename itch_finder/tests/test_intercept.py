import pytest

from itch_finder import intercept
from itch_finder.models import Post
from itch_finder.signals import score_post

NOW = 1_800_000_000.0


def scored(pid, created, title="Is there a tool to merge invoices? Frustrated", source="hn"):
    return score_post(Post(source=source, post_id=pid, title=title, body="x" * 2000,
                           url=f"https://x/{pid}", comments=0, upvotes=0, created_utc=created))


def test_add_fresh_queues_new_posts_without_mutating():
    queue = intercept.empty_queue()
    updated, added = intercept.add_fresh(queue, [scored("1", NOW - 60)], NOW - 3600, "excel", NOW)
    assert queue["items"] == []
    assert [i["id"] for i in added] == ["hn:1"]
    item = updated["items"][0]
    assert item["status"] == "new" and item["offer"] is None and item["niche"] == "excel"
    assert len(item["body"]) == intercept.BODY_KEEP


def test_add_fresh_skips_known_and_stale_posts():
    queue, _ = intercept.add_fresh(intercept.empty_queue(), [scored("1", NOW - 60)],
                                   NOW - 3600, "excel", NOW)
    again, added = intercept.add_fresh(queue, [scored("1", NOW - 60), scored("2", NOW - 7200)],
                                       NOW - 3600, "excel", NOW)
    assert added == []
    assert len(again["items"]) == 1


def test_add_fresh_only_queues_posts_asking_for_help():
    posts = [scored("1", NOW, title="I take notes as a VC, and the app I built for it. Frustrated"),
             scored("2", NOW, title="How do I stop my VBA macro crashing? Frustrated"),
             scored("3", NOW, title="Macro frustrating", source="stackexchange")]
    _, added = intercept.add_fresh(intercept.empty_queue(), posts, 0, "excel", NOW)
    assert sorted(i["id"] for i in added) == ["hn:2", "stackexchange:3"]


def test_mark_sets_status_and_offer():
    queue, _ = intercept.add_fresh(intercept.empty_queue(), [scored("1", NOW)], 0, "excel", NOW)
    marked = intercept.mark(queue, "hn:1", "replied", offer="Kit")
    assert queue["items"][0]["status"] == "new"
    assert marked["items"][0]["status"] == "replied"
    assert marked["items"][0]["offer"] == "Kit"


def test_mark_rejects_unknown_id_and_status():
    queue, _ = intercept.add_fresh(intercept.empty_queue(), [scored("1", NOW)], 0, "excel", NOW)
    with pytest.raises(ValueError):
        intercept.mark(queue, "hn:404", "replied")
    with pytest.raises(ValueError):
        intercept.mark(queue, "hn:1", "posted")


def test_replies_by_offer_counts_replied_items_per_source():
    posts = [scored("1", NOW), scored("2", NOW), scored("3", NOW, source="reddit")]
    queue, _ = intercept.add_fresh(intercept.empty_queue(), posts, 0, "excel", NOW)
    for iid in ("hn:1", "hn:2", "reddit:3"):
        queue = intercept.mark(queue, iid, "replied", offer="Kit")
    assert intercept.replies_by_offer(queue) == {("Kit", "hn"): 2, ("Kit", "reddit"): 1}


def test_load_save_roundtrip_and_corrupt_file(tmp_path):
    path = tmp_path / "q.json"
    queue, _ = intercept.add_fresh(intercept.empty_queue(), [scored("1", NOW)], 0, "excel", NOW)
    intercept.save(queue, path)
    assert intercept.load(path) == queue
    path.write_text("{nope", encoding="utf-8")
    with pytest.raises(ValueError):
        intercept.load(path)
