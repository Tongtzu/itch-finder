from itch_finder import sources
from itch_finder.sources import parse_reddit, parse_hn, parse_stackexchange

SE_FIXTURE = {
    "items": [
        {"question_id": 9, "title": "Excel &quot;SUMIFS&quot; keeps breaking",
         "body": "<p>Every week I fix it <b>manually</b></p>", "link": "https://superuser.com/q/9",
         "answer_count": 2, "score": 5, "creation_date": 1700000000},
        {"question_id": 10, "title": "", "body": ""},
    ]
}


def test_parse_stackexchange_unescapes_and_skips_empty():
    posts = parse_stackexchange(SE_FIXTURE)
    assert len(posts) == 1
    assert posts[0].title == 'Excel "SUMIFS" keeps breaking'
    assert posts[0].body == "Every week I fix it manually"
    assert posts[0].comments == 2


def test_fetch_reddit_stops_after_block(monkeypatch):
    calls = []

    def fake_get_json(session, url, params):
        calls.append(url)
        return 403, None

    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)
    assert sources.fetch_reddit(["a", "b"], ["q1", "q2"]) == []
    assert len(calls) == 1

REDDIT_FIXTURE = {
    "data": {"children": [
        {"data": {"id": "abc", "title": "Is there a tool for X?", "selftext": "pls",
                  "permalink": "/r/excel/comments/abc/x/", "num_comments": 4,
                  "score": 10, "created_utc": 1700000000.0}},
        {"data": {"id": "def", "title": "", "selftext": "",
                  "permalink": "/r/excel/comments/def/", "num_comments": 0,
                  "score": 0, "created_utc": 1700000001.0}},
    ]}
}

HN_FIXTURE = {
    "hits": [
        {"objectID": "1", "title": "Ask HN: invoicing is a nightmare", "story_text": "<p>Help</p>",
         "num_comments": 12, "points": 30, "created_at_i": 1700000000},
        {"objectID": "2", "title": None, "story_title": "Ask HN: tools",
         "comment_text": "I&#x27;d pay for <i>this</i>", "num_comments": None,
         "points": None, "created_at_i": 1700000002},
    ]
}


def test_parse_reddit_builds_posts_and_skips_empty():
    posts = parse_reddit(REDDIT_FIXTURE)
    assert len(posts) == 1
    assert posts[0].url == "https://www.reddit.com/r/excel/comments/abc/x/"
    assert posts[0].comments == 4


def test_parse_reddit_handles_garbage():
    assert parse_reddit({}) == []
    assert parse_reddit({"data": None}) == []


def test_parse_hn_strips_html_and_uses_story_title_for_comments():
    posts = parse_hn(HN_FIXTURE)
    assert len(posts) == 2
    assert posts[0].body == "Help"
    assert posts[1].title == "Ask HN: tools"
    assert posts[1].body == "I'd pay for this"
    assert posts[1].comments == 0
    assert posts[1].url == "https://news.ycombinator.com/item?id=2"


HN_NOISE_FIXTURE = {
    "hits": [
        {"objectID": "10", "title": None, "story_title": "Ask HN: Who is hiring? (October 2026)",
         "comment_text": "Hiring: Excel wizard, frustrating legacy sheets", "created_at_i": 1},
        {"objectID": "11", "title": "Xorg-server 26.1.0 rc1", "story_text": None,
         "url": "https://example.com", "created_at_i": 1},
        {"objectID": "12", "title": "Show HN: I built an Excel thing", "story_text": "<p>Try it</p>",
         "created_at_i": 1},
        {"objectID": "13", "title": "Ask HN: Excel reports eat my week", "story_text": "<p>Ugh</p>",
         "created_at_i": 1},
    ]
}


def test_parse_hn_drops_megathreads_link_stories_and_maker_posts():
    posts = parse_hn(HN_NOISE_FIXTURE)
    assert [p.post_id for p in posts] == ["13"]


def test_parse_hn_must_mention_checks_comment_body_not_story_title():
    payload = {"hits": [
        {"objectID": "20", "title": None, "story_title": "Excel is dead",
         "comment_text": "AI payoff is zero", "created_at_i": 1},
        {"objectID": "21", "title": None, "story_title": "Unrelated",
         "comment_text": "I'd pay to stop fixing EXCEL macros", "created_at_i": 1},
    ]}
    posts = parse_hn(payload, must_mention="excel")
    assert [p.post_id for p in posts] == ["21"]
