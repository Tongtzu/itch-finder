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

VERSION = "0.3"
USER_AGENT = f"python:itch-finder:v{VERSION} (read-only market research)"
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
# Recurring HN threads where keyword hits are job ads or status updates, not pain.
_HN_MEGATHREAD = re.compile(
    r"^(ask hn: )?(who is hiring|who wants to be hired|freelancer\? seeking freelancer"
    r"|what are you working on)", re.IGNORECASE)
_HN_MAKER_POST = re.compile(r"^(show|launch) hn\b", re.IGNORECASE)


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


def _hn_noise(hit: dict) -> bool:
    """Link-only news, maker launches and megathread comments carry no buyer pain."""
    if hit.get("comment_text"):
        return bool(_HN_MEGATHREAD.match(hit.get("story_title") or ""))
    return not hit.get("story_text") or bool(_HN_MAKER_POST.match(hit.get("title") or ""))


def parse_hn(payload: dict, must_mention: str | None = None) -> list[Post]:
    """must_mention: keep only hits whose own text names it (a comment's parent title doesn't count)."""
    needle = (must_mention or "").lower()
    posts = []
    for h in (payload or {}).get("hits") or []:
        if _hn_noise(h):
            continue
        title = h.get("title") or h.get("story_title") or ""
        body = _clean(h.get("story_text") or h.get("comment_text"))
        if not (title.strip() or body):
            continue
        own_text = body if h.get("comment_text") else f"{title} {body}"
        if needle not in own_text.lower():
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


def _session(user_agent: str = USER_AGENT) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = user_agent
    return s


def reddit_user_agent(username: str) -> str:
    """Reddit's required format: <platform>:<app id>:<version> (by /u/<username>)."""
    return f"python:itch-finder:v{VERSION} (by /u/{username})"


def _normalise_sub(sub: str) -> str:
    return sub.strip().lower().removeprefix("r/")


def allowed_subreddits() -> frozenset[str]:
    """The subreddits declared in the Reddit API application; no others are ever queried."""
    raw = os.environ.get("REDDIT_ALLOWED_SUBS", "")
    return frozenset(_normalise_sub(s) for s in raw.split(",") if s.strip())


def _reddit_credentials() -> tuple[str, str, str] | None:
    values = tuple(os.environ.get(n, "").strip()
                   for n in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME"))
    return values if all(values) else None


def _reddit_oauth(session: requests.Session, client_id: str, secret: str) -> bool:
    """Get an app-only OAuth token; Reddit data is only read through the approved API."""
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
    """Search subreddits through Reddit's approved OAuth API only, never the public web pages."""
    subs = [_normalise_sub(s) for s in subs]
    creds = _reddit_credentials()
    if creds is None:
        log.warning("Skipping Reddit: it needs approved API access. Once Reddit approves the "
                    "app, set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET and REDDIT_USERNAME.")
        return []
    undeclared = sorted(set(subs) - allowed_subreddits())
    if undeclared:
        raise ValueError(f"r/{', r/'.join(undeclared)} not in REDDIT_ALLOWED_SUBS; only query "
                         "the subreddits declared in your Reddit API application")
    client_id, secret, username = creds
    session, posts = _session(reddit_user_agent(username)), []
    if not _reddit_oauth(session, client_id, secret):
        return []
    queries = list(queries)
    for sub in subs:
        for q in queries:
            status, payload = _get_json(session, REDDIT_OAUTH_URL.format(sub=sub), {
                "q": q, "restrict_sr": 1, "sort": "new", "limit": PAGE_SIZE,
                "t": "month" if days <= 31 else "year"})
            if status in BLOCKED_STATUSES:
                log.warning("Reddit refused the request (HTTP %s); stopping Reddit for this run.",
                            status)
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


def fetch_hn(queries: Iterable[str], days: int = LOOKBACK_DAYS,
             must_mention: str | None = None) -> list[Post]:
    session, posts = _session(), []
    since = int(time.time()) - days * 86400
    for q in queries:
        _, payload = _get_json(session, HN_URL, {
            "query": q, "tags": "(story,comment)", "hitsPerPage": PAGE_SIZE,
            "numericFilters": f"created_at_i>{since}"})
        posts.extend(parse_hn(payload or {}, must_mention))
        time.sleep(REQUEST_DELAY_S / 2)
    return posts


def dedupe(posts: Iterable[Post]) -> list[Post]:
    seen: dict[tuple[str, str], Post] = {}
    for p in posts:
        seen.setdefault((p.source, p.post_id), p)
    return list(seen.values())
