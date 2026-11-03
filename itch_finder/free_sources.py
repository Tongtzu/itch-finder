"""Free, terms-checked sources: your Google Alerts feeds, GitHub issues and Bluesky posts.

Checked 2026-11-03:
- Google Alerts: your own alert feed (RSS/Atom delivery), so nothing is scraped.
- GitHub: API use is allowed; its policy forbids using the data to contact users
  ("unsolicited emails"), so GitHub results are for research only and are never queued for replies.
- Bluesky: read-only search is fine; its developer guidelines ban automated interactions, so
  replies are always typed by a person. Search needs a free account and an app password.
"""
import logging
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import requests

from itch_finder.models import Post
from itch_finder.sources import (BLOCKED_STATUSES, LOOKBACK_DAYS, REQUEST_DELAY_S, TIMEOUT_S,
                                 _clean, _get_json, _session)

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
GITHUB_SEARCH_URL = "https://api.github.com/search/issues"
GITHUB_QUERY = '"{niche}" in:title'  # body matches pulled in unrelated issues
GITHUB_UNAUTH_DELAY_S = 6.0  # unauthenticated search allows 10 requests a minute
BSKY_SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
BSKY_SEARCH_URL = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
BSKY_TITLE_CHARS = 120
PAGE_SIZE = 50


def _ts(value: str | None) -> float:
    """ISO-8601 timestamp to epoch seconds; 0.0 when missing or malformed."""
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# --- Google Alerts -----------------------------------------------------------------------------

def _unwrap_google(href: str) -> str:
    """Alert links go through google.com/url?url=<real link>; keep the real link."""
    return parse_qs(urlparse(href).query).get("url", [href])[0]


def parse_alerts(xml_text: str) -> list[Post]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("Google Alerts feed is not valid XML: %s", exc)
        return []
    posts = []
    for entry in root.iter(f"{ATOM}entry"):
        title = _clean(entry.findtext(f"{ATOM}title"))
        if not title:
            continue
        link = entry.find(f"{ATOM}link")
        url = _unwrap_google(link.get("href", "")) if link is not None else ""
        posts.append(Post(
            source="google_alerts", post_id=entry.findtext(f"{ATOM}id") or url, title=title,
            body=_clean(entry.findtext(f"{ATOM}content")), url=url, comments=0, upvotes=0,
            created_utc=_ts(entry.findtext(f"{ATOM}published")),
        ))
    return posts


def fetch_alerts(feed_urls: Iterable[str], days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    cutoff = _since(days).timestamp()
    for url in feed_urls:
        if not url.startswith("https://"):
            raise ValueError(f"feed URLs must start with https:// (got {url!r})")
        try:
            resp = session.get(url, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            log.warning("Feed request failed for %s: %s", url, exc)
            continue
        if resp.status_code != 200:
            log.warning("HTTP %s from feed %s", resp.status_code, url)
            continue
        posts += [p for p in parse_alerts(resp.text) if p.created_utc >= cutoff]
        time.sleep(REQUEST_DELAY_S / 2)
    return posts


# --- GitHub issues (research only) -------------------------------------------------------------

def parse_github(payload: dict) -> list[Post]:
    posts = []
    for item in payload.get("items", []):
        if "pull_request" in item:
            continue
        title = _clean(item.get("title"))
        if not title:
            continue
        posts.append(Post(
            source="github", post_id=str(item.get("id", "")), title=title,
            body=_clean(item.get("body")), url=item.get("html_url") or "",
            comments=int(item.get("comments") or 0),
            upvotes=int((item.get("reactions") or {}).get("+1") or 0),
            created_utc=_ts(item.get("created_at")),
        ))
    return posts


def fetch_github(queries: Iterable[str], days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    session.headers["Accept"] = "application/vnd.github+json"
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    delay = REQUEST_DELAY_S if token else GITHUB_UNAUTH_DELAY_S
    since = _since(days).date().isoformat()
    for q in queries:
        status, payload = _get_json(session, GITHUB_SEARCH_URL, {
            "q": f"{q} is:issue is:open created:>={since}", "sort": "reactions-+1",
            "order": "desc", "per_page": PAGE_SIZE})
        if status in BLOCKED_STATUSES:
            log.warning("GitHub refused the request (HTTP %s); stopping GitHub for this run.", status)
            return posts
        posts.extend(parse_github(payload or {}))
        time.sleep(delay)
    return posts


# --- Bluesky -----------------------------------------------------------------------------------

def _bsky_link(uri: str) -> str:
    """at://<did>/app.bsky.feed.post/<rkey> -> web link (uses the DID, not the handle)."""
    parts = uri.removeprefix("at://").split("/")
    return f"https://bsky.app/profile/{parts[0]}/post/{parts[-1]}" if len(parts) == 3 else ""


def parse_bluesky(payload: dict) -> list[Post]:
    posts = []
    for post in payload.get("posts", []):
        record = post.get("record") or {}
        text = _clean(record.get("text"))
        uri = post.get("uri") or ""
        if not text or not uri:
            continue
        posts.append(Post(
            source="bluesky", post_id=uri, title=text[:BSKY_TITLE_CHARS], body=text,
            url=_bsky_link(uri), comments=int(post.get("replyCount") or 0),
            upvotes=int(post.get("likeCount") or 0), created_utc=_ts(record.get("createdAt")),
        ))
    return posts


def _bluesky_login(session: requests.Session) -> bool:
    handle = os.environ.get("BLUESKY_HANDLE", "").strip()
    password = os.environ.get("BLUESKY_APP_PASSWORD", "").strip()
    if not (handle and password):
        log.warning("Skipping Bluesky: search needs BLUESKY_HANDLE and BLUESKY_APP_PASSWORD "
                    "(a free account; create the app password under Settings > Privacy and security).")
        return False
    try:
        resp = session.post(BSKY_SESSION_URL, json={"identifier": handle, "password": password},
                            timeout=TIMEOUT_S)
        token = resp.json().get("accessJwt") if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as exc:
        log.warning("Bluesky login failed: %s", exc)
        return False
    if not token:
        log.warning("Bluesky login returned HTTP %s; check the handle and app password",
                    resp.status_code)
        return False
    session.headers["Authorization"] = f"Bearer {token}"
    return True


def fetch_bluesky(queries: Iterable[str], days: int = LOOKBACK_DAYS) -> list[Post]:
    session, posts = _session(), []
    if not _bluesky_login(session):
        return posts
    since = _since(days).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in queries:
        status, payload = _get_json(session, BSKY_SEARCH_URL,
                                    {"q": q, "since": since, "sort": "latest", "limit": PAGE_SIZE})
        if status in BLOCKED_STATUSES:
            log.warning("Bluesky refused the request (HTTP %s); stopping Bluesky for this run.", status)
            return posts
        posts.extend(parse_bluesky(payload or {}))
        time.sleep(REQUEST_DELAY_S)
    return posts
