"""Demand interception: queue fresh help-seeking posts so you can answer them first."""
import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from itch_finder.models import ScoredPost

DEFAULT_QUEUE = Path("itch_queue.json")
BODY_KEEP = 600  # enough context to write a reply; the full post stays on the platform
RETENTION_DAYS = 30  # keep platform text only as long as it's useful for replying
DAY_S = 86400
STATUSES = frozenset({"new", "drafted", "replied", "skipped"})
TRACKING_FIELDS = ("id", "source", "status", "offer", "found_at")  # no post text
QUESTION_SOURCES = frozenset({"stackexchange"})  # every post there is already a question
ASKS_FOR_HELP = re.compile(
    r"\b(is there (a|an|any)|how (do|can|would|should) (i|we|you)|anyone (know|have|else)"
    r"|looking for (a|an)|any (recommendations|suggestions|ideas)|recommend (a|an)|need help"
    r"|can (someone|anyone)|what('s| is) the best way)\b", re.IGNORECASE)


def asks_for_help(sp: ScoredPost) -> bool:
    """Only someone asking can be answered; launches and opinions are not demand to intercept."""
    p = sp.post
    return p.source in QUESTION_SOURCES or bool(ASKS_FOR_HELP.search(p.text))


def empty_queue() -> dict:
    return {"items": []}


def load(path: Path = DEFAULT_QUEUE) -> dict:
    if not path.exists():
        return empty_queue()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Queue {path} is unreadable: {exc}") from exc
    return {"items": list(data.get("items", []))}


def expire(queue: dict, now: float, days: int = RETENTION_DAYS) -> dict:
    """Drop items older than `days`; replied ones keep only the fields conversion tracking needs."""
    cutoff = now - days * DAY_S
    kept = []
    for item in queue["items"]:
        if item.get("found_at", now) >= cutoff:
            kept.append(item)
        elif item.get("status") == "replied":
            kept.append({k: item.get(k) for k in TRACKING_FIELDS})
    return {**queue, "items": kept}


def save(queue: dict, path: Path = DEFAULT_QUEUE) -> None:
    path.write_text(json.dumps(queue, indent=2), encoding="utf-8")


def _item(sp: ScoredPost, niche: str, now: float) -> dict:
    p = sp.post
    return {
        "id": f"{p.source}:{p.post_id}", "niche": niche, "source": p.source, "url": p.url,
        "title": p.title, "body": p.body[:BODY_KEEP], "score": sp.total, "money": sp.money,
        "urgency": sp.urgency, "created_utc": p.created_utc, "found_at": now,
        "status": "new", "offer": None,
    }


def add_fresh(queue: dict, scored: Iterable[ScoredPost], since: float, niche: str,
              now: float) -> tuple[dict, list[dict]]:
    """Return (new queue, newly added items): posts created after `since` not queued before."""
    known = {i["id"] for i in queue["items"]}
    added = []
    for sp in scored:
        item = _item(sp, niche, now)
        if item["id"] in known or sp.post.created_utc <= since or not asks_for_help(sp):
            continue
        known.add(item["id"])
        added.append(item)
    added.sort(key=lambda i: -i["score"])
    return {**queue, "items": [*queue["items"], *added]}, added


def mark(queue: dict, item_id: str, status: str, offer: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status!r}; use one of {sorted(STATUSES)}")
    if not any(i["id"] == item_id for i in queue["items"]):
        raise ValueError(f"No queued post with id {item_id!r}")
    items = [{**i, "status": status, "offer": offer or i["offer"]} if i["id"] == item_id else i
             for i in queue["items"]]
    return {**queue, "items": items}


def with_status(queue: dict, status: str) -> list[dict]:
    return [i for i in queue["items"] if i["status"] == status]


def replies_by_offer(queue: dict) -> Counter:
    """How many replied posts mentioned each (offer, source) pair."""
    return Counter((i["offer"], i["source"]) for i in with_status(queue, "replied") if i["offer"])
