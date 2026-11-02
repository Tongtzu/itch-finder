"""Sales ledger: track revenue toward the $400 sprint and $10k engine goals."""
import json
import logging
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

log = logging.getLogger(__name__)

SPRINT_GOAL = 400
ENGINE_GOAL = 10_000
SCALE_MIN_SALES = 3
DEFAULT_LEDGER = Path("itch_finder_ledger.json")
UNKNOWN_SOURCE = "unknown"


def empty_ledger() -> dict:
    return {"sales": [], "launched": []}


def load(path: Path = DEFAULT_LEDGER) -> dict:
    if not path.exists():
        return empty_ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Ledger {path} is unreadable: {exc}") from exc
    return {"sales": list(data.get("sales", [])), "launched": list(data.get("launched", []))}


def save(ledger: dict, path: Path = DEFAULT_LEDGER) -> None:
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def launch(ledger: dict, offer: str) -> dict:
    if not offer.strip():
        raise ValueError("Offer name is required")
    if offer in ledger["launched"]:
        return ledger
    return {**ledger, "launched": [*ledger["launched"], offer]}


def record_sale(ledger: dict, offer: str, amount: float, source: str | None = None) -> dict:
    if not offer.strip():
        raise ValueError("Offer name is required")
    if amount <= 0:
        raise ValueError("Sale amount must be positive")
    with_offer = launch(ledger, offer)
    sale = {"offer": offer, "amount": float(amount), **({"source": source} if source else {})}
    return {**with_offer, "sales": [*ledger["sales"], sale]}


def progress(ledger: dict) -> dict:
    revenue = sum(s["amount"] for s in ledger["sales"])
    return {
        "revenue": revenue,
        "sprint_done": revenue >= SPRINT_GOAL,
        "sprint_left": max(SPRINT_GOAL - revenue, 0),
        "engine_pct": revenue / ENGINE_GOAL * 100,
    }


def verdicts(ledger: dict, min_sales: int = SCALE_MIN_SALES) -> dict[str, str]:
    counts = Counter(s["offer"] for s in ledger["sales"])
    offers = dict.fromkeys([*ledger["launched"], *counts])
    return {o: "SCALE" if counts[o] >= min_sales else "WATCH" if counts[o] else "KILL"
            for o in offers}


def conversions(ledger: dict, replies: Mapping[tuple[str, str], int]) -> list[dict]:
    """Sales and replies per (offer, source), best revenue first: what actually converts."""
    sales, revenue = Counter(), Counter()
    for s in ledger["sales"]:
        pair = (s["offer"], s.get("source") or UNKNOWN_SOURCE)
        sales[pair] += 1
        revenue[pair] += s["amount"]
    rows = []
    for pair in dict.fromkeys([*sales, *replies]):
        n = replies.get(pair, 0)
        rows.append({"offer": pair[0], "source": pair[1], "sales": sales[pair],
                     "revenue": revenue[pair], "replies": n,
                     "rate": round(sales[pair] / n, 4) if n else None})
    return sorted(rows, key=lambda r: (-r["revenue"], -(r["rate"] or 0), r["offer"], r["source"]))


def replicate(rows: list[dict]) -> dict | None:
    """The (offer, source) pair to copy next: the top earner, if anything has sold yet."""
    return next((r for r in rows if r["sales"]), None)
