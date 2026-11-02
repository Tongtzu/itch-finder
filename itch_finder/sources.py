"""Fetch public posts from Reddit, Hacker News (Algolia) and Stack Exchange."""
import html
import logging
import os
import re
import time
from collections.abc import Iterable

import requests

from itch_finder.models import Post

log = logging.getLogger(__name__)

USER_AGENT = "itch-finder/0.1 (public market-research script)"
REDDIT_URL = "https://www.reddit.com/r/{sub}/search.json"
REDDIT_OAUTH_URL = "https://oauth.reddit.com/r/{sub}/search"
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
HN_URL = "https://hn.algolia.com/api/v1/search_by_date"
SE_URL = "https://api.stackexchange.com/2.3/search/advanced"
BLOCKED_STATUSES = frozenset({401, 403, 429})
REQUEST_DELAY_S = 2.0
TIMEOUT_S = 15
LOOKBACK_DAYS = 30
PAGE_SIZE = 50
SE_PAGE_SIZE = 100

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _clean(raw: str | None) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", raw or ""))).strip()


def parse_reddit(payload: dict) -> list[Post]:
    children = ((payload or {}).get("data") or {}).get("children") or []
    posts = []
    for child in children:
        d = child.get("data") or {}
        title, body = d.get("title") or "", d.get("selftext") or ""
        if not (title.strip() or body.strip()):
            continue
        posts.append(Post(
            source="reddit", post_id=str(d.get("id", "")), title=title, body=body,
            url="https://www.reddit.com" + (d.get("permalink") or ""),
            comments=int(d.get("num_comments") or 0), upvotes=int(d.get("score") or 0),
            created_utc=float(d.get("created_utc") or 0),
        ))
    return posts


def parse_hn(payload: dict) -> list[Post]:
    posts = []
    for h in (payload or {}).get("hits") or []:
        title = h.get("title") or h.get("story_title") or ""
        body = _clean(h.get("story_text") or h.get("comment_text"))
        if not (title.strip() or body):
            continue
        posts.append(Post(
            source="hn", post_id=str(h.get("objectID", "")), title=title, body=body,
            url=f"https://news.ycombinator.com/item?id={h.get('objectID', '')}",
            comments=int(h.get("num_comments") or 0), upvotes=int(h.get("points") or 0),
            created_utc=float(h.get("created_at_i") or 0),
        ))
    return posts


def parse_stackexchange(payload: dict) -> list[Post]:
    posts = []
    for q in (payload or {}).get("items") or []:
        title = html.unescape(q.get("title") or "")
        body = _clean(q.get("body"))
        if not (title.strip() or body):
            continue
        posts.append(Post(
            source="stackexchange", post_id=str(q.get("question_id", "")), title=title, body=body,
            url=q.get("link") or "", comments=int(q.get("answer_count") or 0),
            upvotes=int(q.get("score") or 0), created_utc=float(q.get("creation_date") or 0),
        ))
    return posts


def _get_json(session: requests.Session, url: str, params: dict) -> tuple[int, dict | None]:
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        log.warning("Request failed for %s: %s", url, exc)
        return 0, None
    if resp.status_code != 200:
        log.warning("HTTP %s from %s (params=%s)", resp.status_code, url, params)
        return resp.status_code, None
    try:
        return 200, resp.json()
    except ValueError:
        log.warning("Non-JSON response from %s", url)
        return 200, None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _reddit_oauth(session: requests.Session) -> bool:
    """Use an app-only OAuth token when REDDIT_CLIENT_ID/SECRET are set."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (client_id and secret):
        return False
    try:
        resp = session.post(REDDIT_TOKEN_URL, auth=(client_id, secret),
                            data={"grant_type": "client_credentials"}, timeout=TIMEOUT_S)
        token = resp.json().get("access_token") if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as exc:
        log.warning("Reddit OAuth failed: %s", exc)
        return False
    if not token:
        log.warning("Reddit OAuth returned HTTP %s; check REDDIT_CLIENT_ID/SECRET", resp.status_code)
        return False
    session.headers["Authorization"] = f"bearer {token}"
    return True


def fetch_reddit(subs: Iterable[str], queries: Iterable[str],
                 days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    url = REDDIT_OAUTH_URL if _reddit_oauth(session) else REDDIT_URL
    queries = list(queries)
    for sub in subs:
        for q in queries:
            status, payload = _get_json(session, url.format(sub=sub), {
                "q": q, "restrict_sr": 1, "sort": "new", "limit": PAGE_SIZE,
                "t": "month" if days <= 31 else "year"})
            if status in BLOCKED_STATUSES:
                log.warning("Reddit blocked the request. Set REDDIT_CLIENT_ID and "
                            "REDDIT_CLIENT_SECRET (free 'script' app at "
                            "https://www.reddit.com/prefs/apps) to enable it.")
                return posts
            posts.extend(parse_reddit(payload or {}))
            time.sleep(REQUEST_DELAY_S)
    return posts


def fetch_stackexchange(sites: Iterable[str], queries: Iterable[str],
                        days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    since = int(time.time()) - days * 86400
    queries = list(queries)
    for site in sites:
        for q in queries:
            match = {"tagged": q} if " " not in q.strip() else {"q": q}
            status, payload = _get_json(session, SE_URL, {
                **match, "site": site, "order": "desc", "sort": "creation",
                "pagesize": SE_PAGE_SIZE, "fromdate": since, "filter": "withbody"})
            if status in BLOCKED_STATUSES:
                log.warning("Stack Exchange throttled this IP; try again later.")
                return posts
            posts.extend(parse_stackexchange(payload or {}))
            time.sleep(REQUEST_DELAY_S / 2)
    return posts


def fetch_hn(queries: Iterable[str], days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    since = int(time.time()) - days * 86400
    for q in queries:
        _, payload = _get_json(session, HN_URL, {
            "query": q, "tags": "(story,comment)", "hitsPerPage": PAGE_SIZE,
            "numericFilters": f"created_at_i>{since}"})
        posts.extend(parse_hn(payload or {}))
        time.sleep(REQUEST_DELAY_S / 2)
    return posts


def dedupe(posts: Iterable[Post]) -> list[Post]:
    seen: dict[tuple[str, str], Post] = {}
    for p in posts:
        seen.setdefault((p.source, p.post_id), p)
    return list(seen.values())
