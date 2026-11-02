"""CLI: python -m itch_finder {mine,launch,sale,status}."""
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from itch_finder import tracker
from itch_finder.cluster import cluster
from itch_finder.offers import build_stack
from itch_finder.report import render
from itch_finder.signals import qualifying
from itch_finder.sources import dedupe, fetch_hn, fetch_reddit, fetch_stackexchange

REDDIT_QUERIES = ('"is there a tool"', '"is there a way"', '"would pay"',
                  '"struggling with"', "frustrated", '"waste hours"')
HN_TERMS = ("frustrating", "pay for", "is there a tool", "struggling", "hate")
DEFAULT_TOP = 5
DEFAULT_MIN_SCORE = 2.0
DEFAULT_DAYS = 90
REPORT_DIR = Path("itch_reports")


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def cmd_mine(args: argparse.Namespace) -> int:
    subs = _csv(args.subs)
    posts = []
    if subs:
        print(f"Mining r/{', r/'.join(subs)} ({len(subs) * len(REDDIT_QUERIES)} searches)...")
        posts += fetch_reddit(subs, REDDIT_QUERIES, args.days)
    if not args.no_hn:
        print("Mining Hacker News...")
        posts += fetch_hn((f"{args.niche} {t}" for t in HN_TERMS), args.days, args.niche)
    se_sites = _csv(args.se_sites)
    if se_sites:
        print(f"Mining Stack Exchange ({', '.join(se_sites)})...")
        posts += fetch_stackexchange(se_sites, [args.niche], args.days)
    posts = dedupe(posts)
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
    out = REPORT_DIR / f"{args.niche.replace(' ', '-').lower()}-{today}.md"
    out.write_text(render(args.niche, today, len(posts), clusters, stacks, angles), encoding="utf-8")

    print(f"{len(posts)} posts -> {len(scored)} with pain -> {len(clusters)} clusters")
    for i, c in enumerate(clusters, 1):
        print(f"  {i}. {c.keyword:<18} score {c.score:>7}  posts {len(c.posts):>3}  "
              f"buying signals {c.money_hits}")
    print(f"Report: {out.resolve()}")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    tracker.save(tracker.launch(tracker.load(), args.offer))
    print(f"Tracking launch: {args.offer}")
    return 0


def cmd_sale(args: argparse.Namespace) -> int:
    ledger = tracker.record_sale(tracker.load(), args.offer, args.amount)
    tracker.save(ledger)
    return cmd_status(args)


def cmd_status(_: argparse.Namespace) -> int:
    ledger = tracker.load()
    p = tracker.progress(ledger)
    sprint = "DONE" if p["sprint_done"] else f"${p['sprint_left']:.0f} to go"
    print(f"Revenue ${p['revenue']:.2f} | $400 sprint: {sprint} | "
          f"$10k engine: {p['engine_pct']:.1f}%")
    for offer, verdict in tracker.verdicts(ledger).items():
        print(f"  {verdict:<6} {offer}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itch_finder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    mine = sub.add_parser("mine", help="find pain clusters and write an offer report")
    mine.add_argument("--niche", required=True, help='e.g. "excel" or "shopify"')
    mine.add_argument("--subs", default="", help="comma-separated subreddits, e.g. excel,smallbusiness")
    mine.add_argument("--top", type=int, default=DEFAULT_TOP, help="number of clusters")
    mine.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    mine.add_argument("--days", type=int, default=DEFAULT_DAYS, help="lookback window")
    mine.add_argument("--no-hn", action="store_true", help="skip Hacker News")
    mine.add_argument("--se-sites", default="superuser,stackoverflow",
                      help="comma-separated Stack Exchange sites ('' to skip)")
    mine.add_argument("--llm", action="store_true", help="add AI angles (needs OPENROUTER_API_KEY)")
    mine.set_defaults(func=cmd_mine)

    launch = sub.add_parser("launch", help="mark an offer as live")
    launch.add_argument("offer")
    launch.set_defaults(func=cmd_launch)

    sale = sub.add_parser("sale", help="log a sale")
    sale.add_argument("offer")
    sale.add_argument("amount", type=float)
    sale.set_defaults(func=cmd_sale)

    sub.add_parser("status", help="revenue and SCALE/WATCH/KILL verdicts").set_defaults(func=cmd_status)
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
