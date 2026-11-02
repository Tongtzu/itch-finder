"""CLI: python -m itch_finder {mine,intercept,drafts,replied,skip,launch,sale,status}."""
import argparse
import logging
import math
import sys
import time
from datetime import date, datetime
from pathlib import Path

from itch_finder import intercept, tracker
from itch_finder.cluster import cluster
from itch_finder.drafts import render as render_drafts
from itch_finder.models import Post
from itch_finder.offers import build_stack
from itch_finder.report import render
from itch_finder.signals import qualifying
from itch_finder.sources import dedupe, fetch_hn, fetch_reddit, fetch_stackexchange
from itch_finder.storefront import render_listings

REDDIT_QUERIES = ('"is there a tool"', '"is there a way"', '"would pay"',
                  '"struggling with"', "frustrated", '"waste hours"')
HN_TERMS = ("frustrating", "pay for", "is there a tool", "struggling", "hate")
DEFAULT_TOP = 5
DEFAULT_MIN_SCORE = 2.0
DEFAULT_DAYS = 90
DEFAULT_SE_SITES = "superuser,stackoverflow"
DEFAULT_HOURS = 48
DEFAULT_INTERCEPT_MIN_SCORE = 1.0  # asks_for_help already filters; don't drop real questions
MIN_EVERY_MINUTES = 10  # polite polling floor for the public APIs
DEFAULT_DRAFT_LIMIT = 10
SHOW_NEW = 10
REPORT_DIR = Path("itch_reports")
DRAFT_DIR = Path("itch_drafts")
LISTING_DIR = Path("itch_listings")


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _gather(niche: str, subs: list[str], se_sites: list[str], use_hn: bool,
            days: int) -> list[Post]:
    posts = []
    if subs:
        print(f"Mining r/{', r/'.join(subs)} ({len(subs) * len(REDDIT_QUERIES)} searches)...")
        posts += fetch_reddit(subs, REDDIT_QUERIES, days)
    if use_hn:
        print("Mining Hacker News...")
        posts += fetch_hn((f"{niche} {t}" for t in HN_TERMS), days, niche)
    if se_sites:
        print(f"Mining Stack Exchange ({', '.join(se_sites)})...")
        posts += fetch_stackexchange(se_sites, [niche], days)
    return dedupe(posts)


def _slug(niche: str) -> str:
    return niche.replace(" ", "-").lower()


def cmd_mine(args: argparse.Namespace) -> int:
    subs = _csv(args.subs)
    posts = _gather(args.niche, subs, _csv(args.se_sites), not args.no_hn, args.days)
    if not posts:
        print("No posts fetched (blocked, offline, or empty niche). See warnings above.")
        return 1

    scored = qualifying(posts, args.min_score)
    exclude = frozenset(_csv(args.niche.replace(" ", ",")) + subs)
    clusters = cluster(scored, args.top, exclude)
    stacks = {c.keyword: build_stack(c, args.niche) for c in clusters}
    angles = {}
    if args.llm:
        from itch_finder.llm import angle_for
        angles = {c.keyword: angle_for(c, args.niche) for c in clusters}

    today = date.today().isoformat()
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"{_slug(args.niche)}-{today}.md"
    out.write_text(render(args.niche, today, len(posts), clusters, stacks, angles), encoding="utf-8")

    print(f"{len(posts)} posts -> {len(scored)} with pain -> {len(clusters)} clusters")
    for i, c in enumerate(clusters, 1):
        print(f"  {i}. {c.keyword:<18} score {c.score:>7}  posts {len(c.posts):>3}  "
              f"buying signals {c.money_hits}")
    print(f"Report: {out.resolve()}")
    if args.brand and stacks:
        LISTING_DIR.mkdir(exist_ok=True)
        listings = LISTING_DIR / f"{_slug(args.niche)}-{today}.md"
        listings.write_text(render_listings(args.brand, args.niche, today, stacks), encoding="utf-8")
        print(f"Store listings: {listings.resolve()}")
    return 0


def _intercept_once(args: argparse.Namespace, days: int) -> None:
    posts = _gather(args.niche, _csv(args.subs), _csv(args.se_sites), not args.no_hn, days)
    now = time.time()
    scored = qualifying(posts, args.min_score)
    queue, added = intercept.add_fresh(intercept.load(), scored, now - args.hours * 3600,
                                       args.niche, now)
    intercept.save(queue)
    waiting = len(intercept.with_status(queue, "new"))
    print(f"{len(posts)} posts checked -> {len(added)} new to answer ({waiting} waiting in queue)")
    for item in added[:SHOW_NEW]:
        print(f"  {item['score']:>6}  {item['id']:<26} {item['title'][:70]}")
        print(f"          {item['url']}")
    if added:
        print("Next: python -m itch_finder drafts")


def cmd_intercept(args: argparse.Namespace) -> int:
    if args.every and args.every < MIN_EVERY_MINUTES:
        raise ValueError(f"--every must be at least {MIN_EVERY_MINUTES} minutes")
    days = max(1, math.ceil(args.hours / 24))
    try:
        while True:
            _intercept_once(args, days)
            if not args.every:
                return 0
            print(f"Next check in {args.every} min (Ctrl+C to stop).")
            time.sleep(args.every * 60)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0


def cmd_drafts(args: argparse.Namespace) -> int:
    queue = intercept.load()
    items = intercept.with_status(queue, "new")[:args.limit]
    if not items:
        print("Nothing new to draft. Run: python -m itch_finder intercept --niche <niche>")
        return 0
    replies = {}
    if args.llm:
        from itch_finder.llm import reply_for
        replies = {i["id"]: reply_for(i, i["niche"]) for i in items}
    DRAFT_DIR.mkdir(exist_ok=True)
    out = DRAFT_DIR / f"{datetime.now():%Y-%m-%d-%H%M%S}.md"
    out.write_text(render_drafts(items, replies, args.offer, date.today().isoformat()),
                   encoding="utf-8")
    for item in items:
        queue = intercept.mark(queue, item["id"], "drafted")
    intercept.save(queue)
    print(f"{len(items)} drafts: {out.resolve()}")
    return 0


def cmd_replied(args: argparse.Namespace) -> int:
    intercept.save(intercept.mark(intercept.load(), args.id, "replied", args.offer))
    print(f"Marked replied: {args.id}" + (f" (offer: {args.offer})" if args.offer else ""))
    return 0


def cmd_skip(args: argparse.Namespace) -> int:
    intercept.save(intercept.mark(intercept.load(), args.id, "skipped"))
    print(f"Skipped: {args.id}")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    tracker.save(tracker.launch(tracker.load(), args.offer))
    print(f"Tracking launch: {args.offer}")
    return 0


def cmd_sale(args: argparse.Namespace) -> int:
    ledger = tracker.record_sale(tracker.load(), args.offer, args.amount, args.source)
    tracker.save(ledger)
    return cmd_status(args)


def _print_conversions(ledger: dict) -> None:
    rows = tracker.conversions(ledger, intercept.replies_by_offer(intercept.load()))
    if rows:
        print("What converts (offer / source):")
    for r in rows:
        rate = f"{r['rate']:.0%}" if r["rate"] is not None else "n/a"
        print(f"  {r['offer']} / {r['source']}: {r['sales']} sales, ${r['revenue']:.0f}, "
              f"{r['replies']} replies, {rate} of replies bought")
    best = tracker.replicate(rows)
    if best:
        print(f"Replicate: {best['offer']} via {best['source']}. Intercept more {best['source']} "
              "posts on this topic, reuse the reply that sold, then mine neighbouring communities.")


def cmd_status(_: argparse.Namespace) -> int:
    ledger = tracker.load()
    p = tracker.progress(ledger)
    sprint = "DONE" if p["sprint_done"] else f"${p['sprint_left']:.0f} to go"
    print(f"Revenue ${p['revenue']:.2f} | $400 sprint: {sprint} | "
          f"$10k engine: {p['engine_pct']:.1f}%")
    for offer, verdict in tracker.verdicts(ledger).items():
        print(f"  {verdict:<6} {offer}")
    _print_conversions(ledger)
    return 0


def _add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--niche", required=True, help='e.g. "excel" or "shopify"')
    p.add_argument("--subs", default="", help="comma-separated subreddits, e.g. excel,smallbusiness")
    p.add_argument("--no-hn", action="store_true", help="skip Hacker News")
    p.add_argument("--se-sites", default=DEFAULT_SE_SITES,
                   help="comma-separated Stack Exchange sites ('' to skip)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itch_finder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    mine = sub.add_parser("mine", help="find pain clusters and write an offer report")
    _add_source_args(mine)
    mine.add_argument("--top", type=int, default=DEFAULT_TOP, help="number of clusters")
    mine.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    mine.add_argument("--days", type=int, default=DEFAULT_DAYS, help="lookback window")
    mine.add_argument("--llm", action="store_true", help="add AI angles (needs OPENROUTER_API_KEY)")
    mine.add_argument("--brand", default="", help="also write store listings under this brand name")
    mine.set_defaults(func=cmd_mine)

    icpt = sub.add_parser("intercept", help="queue fresh posts asking for help, to answer first")
    _add_source_args(icpt)
    icpt.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="only posts this recent")
    icpt.add_argument("--min-score", type=float, default=DEFAULT_INTERCEPT_MIN_SCORE)
    icpt.add_argument("--every", type=int, default=0,
                      help=f"repeat every N minutes (min {MIN_EVERY_MINUTES}); Ctrl+C stops")
    icpt.set_defaults(func=cmd_intercept)

    drafts = sub.add_parser("drafts", help="write reply drafts for new queued posts")
    drafts.add_argument("--offer", default="", help="offer to mention in an optional disclosure line")
    drafts.add_argument("--limit", type=int, default=DEFAULT_DRAFT_LIMIT)
    drafts.add_argument("--llm", action="store_true", help="AI-written replies (needs OPENROUTER_API_KEY)")
    drafts.set_defaults(func=cmd_drafts)

    replied = sub.add_parser("replied", help="mark a queued post as answered by you")
    replied.add_argument("id")
    replied.add_argument("--offer", default="", help="offer your reply mentioned")
    replied.set_defaults(func=cmd_replied)

    skip = sub.add_parser("skip", help="drop a queued post")
    skip.add_argument("id")
    skip.set_defaults(func=cmd_skip)

    launch = sub.add_parser("launch", help="mark an offer as live")
    launch.add_argument("offer")
    launch.set_defaults(func=cmd_launch)

    sale = sub.add_parser("sale", help="log a sale")
    sale.add_argument("offer")
    sale.add_argument("amount", type=float)
    sale.add_argument("--source", default="", help="where the buyer came from, e.g. reddit, hn")
    sale.set_defaults(func=cmd_sale)

    sub.add_parser("status", help="revenue, verdicts and what converts").set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
