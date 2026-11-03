import pytest

from itch_finder import free_sources as fs
from itch_finder import intercept, llm
from itch_finder.signals import score_post

ALERT_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:google.com,2013:googlealerts/feed:1</id>
    <title type="html">Is there a tool to merge &lt;b&gt;Excel&lt;/b&gt; sheets?</title>
    <link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://example.com/q/1&amp;ct=ga"/>
    <published>2026-11-01T10:00:00Z</published>
    <content type="html">I waste hours every week doing this manually</content>
  </entry>
  <entry><id>2</id><title></title></entry>
</feed>"""

GITHUB_PAYLOAD = {"items": [
    {"id": 7, "title": "Feature request: export to CSV", "body": "Would be nice",
     "html_url": "https://github.com/o/r/issues/7", "comments": 3,
     "reactions": {"+1": 12}, "created_at": "2026-10-30T00:00:00Z"},
    {"id": 8, "title": "Fix typo", "pull_request": {}, "html_url": "https://github.com/o/r/pull/8"},
]}

BSKY_PAYLOAD = {"posts": [
    {"uri": "at://did:plc:abc123/app.bsky.feed.post/3kxyz", "replyCount": 2, "likeCount": 5,
     "author": {"handle": "someone.bsky.social"},
     "record": {"text": "Is there a tool that does invoices for freelancers? So frustrating",
                "createdAt": "2026-11-02T08:00:00Z"}},
    {"uri": "", "record": {"text": "no uri"}},
]}


def test_parse_alerts_unwraps_google_links_and_cleans_html():
    posts = fs.parse_alerts(ALERT_FEED)
    assert len(posts) == 1
    p = posts[0]
    assert (p.source, p.title, p.url) == ("google_alerts", "Is there a tool to merge Excel sheets?",
                                          "https://example.com/q/1")
    assert p.created_utc > 0
    assert score_post(p).pain > 0


def test_parse_alerts_survives_bad_xml():
    assert fs.parse_alerts("<not xml") == []


def test_fetch_alerts_requires_https():
    with pytest.raises(ValueError, match="https://"):
        fs.fetch_alerts(["http://example.com/feed"])


def test_parse_github_skips_pull_requests_and_counts_thumbs_up():
    posts = fs.parse_github(GITHUB_PAYLOAD)
    assert [(p.source, p.title, p.upvotes, p.comments) for p in posts] == [
        ("github", "Feature request: export to CSV", 12, 3)]


def test_fetch_github_sends_token_and_stops_when_blocked(monkeypatch):
    calls = []

    def fake_get_json(session, url, params):
        calls.append((session.headers.get("Authorization"), params["q"]))
        return 403, None

    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    monkeypatch.setattr(fs, "_get_json", fake_get_json)
    monkeypatch.setattr(fs.time, "sleep", lambda _: None)
    assert fs.fetch_github(["excel"], days=7) == []
    assert len(calls) == 1
    assert calls[0][0] == "Bearer t0ken"
    assert "is:issue is:open created:>=" in calls[0][1]


def test_parse_bluesky_links_by_did_and_never_keeps_the_handle():
    posts = fs.parse_bluesky(BSKY_PAYLOAD)
    assert len(posts) == 1
    p = posts[0]
    assert p.url == "https://bsky.app/profile/did:plc:abc123/post/3kxyz"
    assert "someone" not in p.url + p.title + p.body
    assert (p.comments, p.upvotes) == (2, 5)


def test_fetch_bluesky_without_credentials_makes_no_requests(monkeypatch):
    monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
    monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)

    def no_network(*_a, **_k):
        raise AssertionError("no request without credentials")

    monkeypatch.setattr(fs, "_get_json", no_network)
    assert fs.fetch_bluesky(["excel"]) == []


def test_research_only_sources_are_never_queued_for_replies():
    alert = fs.parse_alerts(ALERT_FEED)[0]
    issue = fs.parse_github(GITHUB_PAYLOAD)[0]
    scored = [score_post(alert), score_post(issue)]
    _, added = intercept.add_fresh({"items": []}, scored, since=0, niche="excel", now=1e10)
    assert added == []


def test_no_ai_replies_for_stack_exchange(monkeypatch):
    monkeypatch.setattr(llm, "_complete", lambda prompt, what: "ai text")
    assert llm.reply_for({"id": "stackexchange:1", "source": "stackexchange", "title": "t",
                          "body": "b"}, "excel") is None
    assert llm.reply_for({"id": "bluesky:1", "source": "bluesky", "title": "t", "body": "b"},
                         "excel") == "ai text"
