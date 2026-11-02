"""Mine job ads you pasted yourself for recurring needs, and say which are sellable as a product.

Job boards such as SEEK forbid scrapers, so this never fetches anything: copy ads into a text
file by hand, separated by a line of `---` (a pasted SEEK results page also works, it splits on
the "Listed ... ago" lines).
"""
import re
from collections import Counter
from dataclasses import dataclass

from itch_finder.cluster import MIN_POSTS, _stem, keywords
from itch_finder.models import Post

SOURCE = "pasted"
TITLE_MAX = 120
PHRASE_TOP = 12
EVIDENCE_TITLES = 5
PILOT_PRICE_AUD = 1500
PILOT_DAYS = 10
SUPPORT_AUD_MONTH = 300
KIT_PRICE_AUD = 29

_DASH_SEP = re.compile(r"^\s*(-{3,}|={3,})\s*$")
_LISTED_SEP = re.compile(r"^\s*listed .+ ago\s*$", re.IGNORECASE)
_RECRUITER = re.compile(r"^recruited by\b", re.IGNORECASE)
_URL = re.compile(r"^https?://\S+$")

JOB_FILLER = frozenset("""
role team salary super hybrid remote contract job experience opportunity position permanent
full part australia melbourne vic sydney day annum apply join benefit recruitment listed
classification subclassification information communication technology engineering developer
programmer senior lead junior associate staff aud per temp skill responsibility environment
solution shape drive group future deliver delivering fixed term exciting impact
""".split())


@dataclass(frozen=True)
class Need:
    name: str
    pattern: str
    deliverable: bool
    why: str
    angle: str = ""


NEEDS = (
    Need("AI agents", r"\bagent(s|ic)?\b", True, "prototype that runs one real workflow",
         "an agent that completes one real workflow end to end, with logging and a human "
         "approval step"),
    Need("Document search / RAG",
         r"\b(rag|retrieval|knowledge base|vector (db|database|search)|embeddings?)\b", True,
         "Q&A over the buyer's own files",
         "a question-answering assistant over your own documents that cites its sources"),
    Need("LLM evaluation", r"\b(evaluat\w*|evals?|benchmark\w*|test sets?)\b", True,
         "test sets and a scoring harness",
         "a test set of real questions with pass/fail scoring you can rerun after every change"),
    Need("Microsoft / Azure / Copilot",
         r"\b(azure|copilot|microsoft|fabric|power (automate|platform))\b", True,
         "buildable, but needs access to the buyer's tenant",
         "an assistant built on your own Azure OpenAI or Microsoft 365 account"),
    Need("Workflow automation", r"\bautomat\w*", True, "scripts and integrations",
         "an automation that removes one repetitive task, such as email triage or quote drafting"),
    Need("Governance & guardrails",
         r"\b(governance|guardrails?|privacy|assurance|responsible ai|risk framework)\b", True,
         "templates and checklists, not a compliance sign-off",
         "an AI use policy, risk register and guardrail checklist you can adapt"),
    Need("Production ops / MLOps",
         r"\b(mlops|devops|kubernetes|eks|on-?call|production-grade|at scale)\b", False,
         "needs ongoing system access and an accountable person"),
    Need("Model training / fine-tuning",
         r"\b(fine-?tun\w*|train(ing)? (models?|llms?)|deep learning|pytorch|tensorflow)\b", False,
         "needs their data and a GPU budget"),
    Need("Computer vision", r"\b(computer vision|perception|image recognition)\b", False,
         "specialist work, often defence"),
    Need("On-device / edge AI", r"\b(on-device|edge devices?|embedded|small computing devices)\b",
         False, "specialist hardware work"),
)

BLOCKERS = {
    "Security clearance": r"\b(security clearance|clearance required|nv[12]|agsva|baseline clear\w*)\b",
    "On-site days": r"\b\d[- ]days?( per week)? in (the )?office\b|\bon-?site\b",
    "Permanent hire": r"\b(permanent|full[- ]time)\b",
    "Work rights / citizenship": r"\b(citizen\w*|work rights)\b",
}


def _chunks(text: str) -> list[list[str]]:
    lines = text.splitlines()
    results_page = any(_LISTED_SEP.match(line) for line in lines)
    chunks, current = [], []
    for line in lines:
        if _DASH_SEP.match(line) or _LISTED_SEP.match(line):
            chunks.append(current)
            current = []
        else:
            current.append(line)
    chunks.append(current)
    return chunks[1:] if results_page else chunks  # a results page starts with search chrome


def _clean(lines: list[str]) -> list[str]:
    """Drop blank lines and recruiter names (a "Recruited by" line and the name after it)."""
    out, skip_name = [], False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if skip_name:
            skip_name = False
            continue
        if _RECRUITER.match(line):
            skip_name = line.lower() == "recruited by"
            continue
        out.append(line)
    return out


def parse_ads(text: str, name: str) -> list[Post]:
    ads = []
    for lines in (_clean(c) for c in _chunks(text)):
        if not lines:
            continue
        url = next((line for line in lines if _URL.match(line)), "")
        body = [line for line in lines[1:] if line != url]
        ads.append(Post(source=SOURCE, post_id=f"{name}#{len(ads) + 1}", title=lines[0][:TITLE_MAX],
                        body="\n".join(body), url=url, comments=0, upvotes=0, created_utc=0.0))
    return ads


def needs(ads: list[Post]) -> list[dict]:
    rows = []
    for order, need in enumerate(NEEDS):
        matched = [a for a in ads if re.search(need.pattern, a.text, re.IGNORECASE)]
        if matched:
            rows.append({"need": need.name, "ads": len(matched), "share": len(matched) / len(ads),
                         "deliverable": need.deliverable, "why": need.why, "angle": need.angle,
                         "titles": tuple(a.title for a in matched), "order": order})
    return sorted(rows, key=lambda r: (-r["ads"], r["order"]))


def blockers_by_ad(ads: list[Post]) -> dict[str, int]:
    counts = {name: sum(1 for a in ads if re.search(pat, a.text, re.IGNORECASE))
              for name, pat in BLOCKERS.items()}
    return {name: n for name, n in counts.items() if n}


def phrases(ads: list[Post], exclude: frozenset[str]) -> list[tuple[str, int]]:
    """Terms that recur across ads, two-word phrases first on ties."""
    skip = frozenset(_stem(w.lower()) for w in exclude | JOB_FILLER)
    df = Counter(t for a in ads for t in keywords(a.text, skip))
    recurring = [(t, n) for t, n in df.items() if n >= MIN_POSTS]
    return sorted(recurring, key=lambda tn: (-tn[1], " " not in tn[0], tn[0]))[:PHRASE_TOP]


def _offers(row: dict) -> list[str]:
    seen = "; ".join(row["titles"][:EVIDENCE_TITLES])
    return [
        f"## Draft offers: {row['need']}", "",
        f"Seen in: {seen}", "",
        "These ads hire a person; they don't buy products. Sell the pilot to smaller businesses "
        "that want the same thing but can't fund that hire, and the kit to people applying for "
        "these roles.", "",
        f"**A. Fixed-price pilot: AUD {PILOT_PRICE_AUD:,}, {PILOT_DAYS} business days**",
        f"- Week 1: {row['angle']}, on the buyer's own account and sample data.",
        "- Week 2: 30 real test cases with pass/fail results, a handover document and a "
        "30-minute walkthrough.",
        f"- Optional: AUD {SUPPORT_AUD_MONTH}/month for fixes.",
        "- Not included: deployment into production systems, security certification, 24/7 support.",
        "",
        f"**B. Portfolio kit for applicants: AUD {KIT_PRICE_AUD}**",
        f"- A ready-to-run code project: {row['angle']}.",
        "- A README written as a case study the buyer can talk through in interviews.",
        "",
    ]


def render(niche: str, date: str, ads: list[Post], exclude: frozenset[str]) -> str:
    rows = needs(ads)
    total = len(ads)
    out = [f"# Job-ad needs: {niche} ({date})", "",
           f"Read {total} pasted job ads. Use this to see which skills are in demand and what a "
           "solo builder could sell around that demand.", "",
           "## Needs", "",
           "| Need | Ads | Share | Deliverable as a product? | Why |", "|---|---|---|---|---|"]
    out += [f"| {r['need']} | {r['ads']} | {r['share']:.0%} | {'yes' if r['deliverable'] else 'no'} "
            f"| {r['why']} |" for r in rows]
    if not rows:
        out.append("| _none matched_ | 0 | 0% | | |")

    blockers = blockers_by_ad(ads)
    out += ["", "## Hiring-only requirements", ""]
    out += [f"- {name}: {n} of {total} ads" for name, n in blockers.items()] or ["_None found._"]

    terms = phrases(ads, exclude)
    out += ["", "## Recurring terms", "",
            ", ".join(f"`{t}` ({n})" for t, n in terms) or "_None recur in two or more ads._", ""]

    top = next((r for r in rows if r["deliverable"]), None)
    out += _offers(top) if top else [
        "_None of the needs found can be delivered as a remote product._", ""]
    out.append("Only sell what you can deliver and support. These are drafts, not sales forecasts.")
    return "\n".join(out) + "\n"
