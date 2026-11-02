"""Turn a pain cluster into a 3-tier offer stack."""
import math

from itch_finder.models import Cluster, Offer

TRIPWIRE_PRICE = 19
CORE_PRICE = 49
DFY_PRICE = 197
DFY_PREMIUM_PRICE = 297
PREMIUM_MONEY_HITS = 2


def build_stack(cluster: Cluster, niche: str) -> tuple[Offer, ...]:
    topic = cluster.keyword.title()
    kw = cluster.keyword
    dfy_price = DFY_PREMIUM_PRICE if cluster.money_hits >= PREMIUM_MONEY_HITS else DFY_PRICE
    return (
        Offer(tier="tripwire", name=f"{topic} Fix Kit", price=TRIPWIRE_PRICE,
              deliverable="PDF checklist + copy-paste templates/prompts for the exact problems people keep posting about",
              build_time="2-4 hours",
              pitch=f"Stop fighting {kw} problems in {niche}: the 15-minute fix, step by step."),
        Offer(tier="core", name=f"{topic} Autopilot Toolkit", price=CORE_PRICE,
              deliverable="Working template (sheet/Notion/script) + screen-recorded walkthrough, no face needed",
              build_time="1-2 days",
              pitch=f"Plug-and-play system so {kw} runs itself instead of eating your week."),
        Offer(tier="done-for-you", name=f"{topic} Done-For-You Setup", price=dfy_price,
              deliverable="You build or fix it for the buyer (async or screenshare), delivered in 48h",
              build_time="1-3 hours per client",
              pitch=f"Send me your {kw} mess, get it working in 48 hours."),
    )


def sales_needed(goal: float, price: float) -> int:
    if goal <= 0:
        return 0
    return math.ceil(goal / price)
