"""Render the ranked pain clusters and offer stacks as a markdown battle plan."""
from itch_finder.models import Cluster, Offer
from itch_finder.offers import sales_needed
from itch_finder.tracker import ENGINE_GOAL, SPRINT_GOAL

EVIDENCE_PER_CLUSTER = 5
TITLE_MAX = 140

PLAYBOOK = f"""## Playbook

**$400 sprint (days 1-7)**
1. Take the #1 cluster with the most buying signals. Don't build anything yet.
2. Make a free product page on Gumroad / Lemon Squeezy / Payhip for the **done-for-you** tier, under
   a faceless brand name. Two or three DFY clients is the fastest way to ${SPRINT_GOAL}.
3. Open each evidence thread and **solve the problem in your reply**. Only mention the offer where the
   community's rules allow it (check the sidebar; many ban self-promo). Put the link on your profile.
4. Package what you learned on those calls into the **tripwire** kit, then sell it to everyone who
   didn't need DFY.
5. Log every sale: `python -m itch_finder sale "<offer>" <amount>`.

**Scale to ${ENGINE_GOAL:,}**
- `python -m itch_finder status` shows each launched offer as SCALE / WATCH / KILL.
- KILL offers with 0 sales after a week of real exposure. Re-mine and try the next cluster.
- SCALE offers: re-mine neighbouring communities for the same keyword, raise the price, add
  the next tier as an upsell, and turn repeated DFY work into a template you can sell.
- Example mix for ${ENGINE_GOAL:,}: 30 DFY at $297 plus 25 toolkits at $49 = $10,135.

These numbers are targets, not predictions. Nothing here guarantees sales.
"""


def _evidence(cluster: Cluster) -> list[str]:
    lines = []
    for s in cluster.posts[:EVIDENCE_PER_CLUSTER]:
        title = s.post.title.replace("[", "(").replace("]", ")")[:TITLE_MAX]
        lines.append(f"- [{title}]({s.post.url}) — {s.total} "
                     f"(pain {s.pain} / money {s.money} / urgency {s.urgency}, {s.post.source})")
    return lines


def _stack_table(stack: tuple[Offer, ...]) -> list[str]:
    rows = ["| Tier | Offer | Price | Deliverable | Build | Sales for $400 |",
            "|---|---|---|---|---|---|"]
    rows += [f"| {o.tier} | **{o.name}**<br>{o.pitch} | ${o.price} | {o.deliverable} | "
             f"{o.build_time} | {sales_needed(SPRINT_GOAL, o.price)} |" for o in stack]
    return rows


def render(niche: str, date: str, fetched: int, clusters: list[Cluster],
           stacks: dict[str, tuple[Offer, ...]], angles: dict[str, str | None]) -> str:
    qualified = sum(len(c.posts) for c in clusters)
    out = [f"# Pain report: {niche} ({date})", "",
           f"Fetched {fetched} public posts. {qualified} showed pain signals, grouped into "
           f"{len(clusters)} clusters ranked by total pain score.", "", PLAYBOOK]
    if not clusters:
        out.append("_No qualifying pain found. Try other communities, a broader niche, or a "
                   "lower `--min-score`._")
    for i, c in enumerate(clusters, 1):
        out += ["", f"## {i}. `{c.keyword}` — score {c.score} · {len(c.posts)} posts · "
                    f"{c.money_hits} with buying signals", ""]
        if angles.get(c.keyword):
            out += ["**AI angle**", "", angles[c.keyword], ""]
        out += ["**Evidence**", "", *_evidence(c), "", *_stack_table(stacks[c.keyword])]
    return "\n".join(out) + "\n"
