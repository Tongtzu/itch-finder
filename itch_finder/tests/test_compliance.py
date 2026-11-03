"""Reddit Responsible Builder Policy safeguards: retention limits and no Reddit text to LLMs."""
from itch_finder import intercept, llm
from itch_finder.models import Cluster, Post, ScoredPost

DAY = 86400
NOW = 100 * DAY


def _item(item_id, status, days_ago):
    return {"id": item_id, "source": "reddit", "url": "https://x", "title": "t", "body": "b",
            "status": status, "offer": "Kit" if status == "replied" else None,
            "found_at": NOW - days_ago * DAY}


def test_expire_drops_old_items_and_strips_text_from_old_replies():
    queue = {"items": [_item("reddit:new", "new", 1), _item("reddit:old", "new", 31),
                       _item("reddit:sold", "replied", 45)]}
    kept = intercept.expire(queue, NOW)["items"]
    assert [i["id"] for i in kept] == ["reddit:new", "reddit:sold"]
    assert kept[1] == {"id": "reddit:sold", "source": "reddit", "status": "replied",
                       "offer": "Kit", "found_at": NOW - 45 * DAY}
    assert queue["items"][1]["id"] == "reddit:old"  # input left unchanged


def _scored(source, title):
    post = Post(source=source, post_id=title, title=title, body="", url="", comments=0,
                upvotes=0, created_utc=0)
    return ScoredPost(post=post, pain=1, money=0, urgency=0, total=1.0)


def test_reddit_text_is_never_sent_to_the_llm(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_complete", lambda prompt, what: sent.append(prompt) or "ok")

    assert llm.reply_for({"id": "reddit:1", "source": "reddit", "title": "t", "body": "b"},
                         "excel") is None
    reddit_only = Cluster(keyword="vba", posts=(_scored("reddit", "Reddit title"),))
    assert llm.angle_for(reddit_only, "excel") is None
    assert sent == []

    mixed = Cluster(keyword="vba", posts=(_scored("reddit", "Reddit title"),
                                          _scored("hn", "HN title")))
    assert llm.angle_for(mixed, "excel") == "ok"
    assert "HN title" in sent[0]
    assert "Reddit title" not in sent[0]
