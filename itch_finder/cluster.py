"""Group scored posts into pain clusters by their most shared keyword."""
import re
from collections import Counter
from collections.abc import Iterable

from itch_finder.models import Cluster, ScoredPost

STOPWORDS = frozenset("""
the and for with that this from have has had are was were been being but not you your
yours they them their what when where which who why how can could would should will just
there here into onto about than then also very really much many more most some any all
our ours its it's i'm i've i'd don't doesn't didn't can't won't isn't anyone someone
something anything everything thing things way ways get got getting make made use using
used need needs want wants like know does did doing one two lot lots time times day days
week month year help please thanks thank question anybody else still even every each
frustrated frustrating struggling struggle hate nightmare tool tools app apps software
manual manually tedious pay paying willing happy happily gladly hire urgent asap deadline
waste wasting wasted hours hour keep keeps breaking crashing failing best good bad new
ask show tell http https www com reddit post edit update people person someone's work
working worked company business year's month's today right sure think thought trying
tried try able without since because while after before over under other another same
able seem seems actually maybe probably basically literally simply quite now find found
stuff see look looking going back first last next around through only same different
create created value values number data file files error errors automate automatically
working work works sheet code example below above following give given set using
start started end ended point put take taken run running issue issues problem problems
out well part add currently case those these once own build built instead involve often
too such may might again already always never via per yet ago etc figured
better useful knowledge reason read though answer answers
""".split())
MIN_POSTS = 2  # a pain has to recur to be worth an offer
PHRASE_BOOST = 2  # a shared two-word phrase names the pain better than either word alone

_WORD = re.compile(r"[a-z][a-z'\-]{2,}")


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def keywords(text: str, exclude: frozenset[str] = frozenset()) -> frozenset[str]:
    """Content words plus adjacent two-word phrases; filler breaks a phrase."""
    seq = [w if len(w) > 2 and w not in STOPWORDS and w not in exclude else None
           for w in (_stem(raw.strip("'-")) for raw in _WORD.findall(text.lower()))]
    phrases = {f"{a} {b}" for a, b in zip(seq, seq[1:]) if a and b and a != b}
    return frozenset({w for w in seq if w} | phrases)


def _pick_labels(df: Counter, weight: Counter, top_n: int) -> list[str]:
    """Best recurring terms first, skipping any that share a word with one already picked."""
    def strength(term: str) -> int:
        return df[term] * (PHRASE_BOOST if " " in term else 1)

    candidates = sorted((t for t in df if df[t] >= MIN_POSTS),
                        key=lambda t: (-strength(t), -weight[t], t))
    picked, used = [], set()
    for term in candidates:
        words = set(term.split())
        if words & used:
            continue
        picked.append(term)
        used |= words
        if len(picked) == top_n:
            break
    return picked


def cluster(posts: Iterable[ScoredPost], top_n: int,
            exclude: frozenset[str] = frozenset()) -> list[Cluster]:
    posts = list(posts)
    if not posts:
        return []
    exclude = frozenset(_stem(e.lower()) for e in exclude)
    tokens = [keywords(p.post.text, exclude) for p in posts]
    df = Counter(w for t in tokens for w in t)
    weight = Counter()
    for p, t in zip(posts, tokens):
        for w in t:
            weight[w] += p.total
    ranked = _pick_labels(df, weight, top_n)
    rank = {w: i for i, w in enumerate(ranked)}

    groups: dict[str, list[ScoredPost]] = {w: [] for w in ranked}
    for p, t in zip(posts, tokens):
        hits = [w for w in t if w in rank]
        if hits:
            groups[min(hits, key=rank.__getitem__)].append(p)

    clusters = [Cluster(keyword=w, posts=tuple(sorted(g, key=lambda s: -s.total)))
                for w, g in groups.items() if len(g) >= MIN_POSTS]
    return sorted(clusters, key=lambda c: (-c.score, c.keyword))
