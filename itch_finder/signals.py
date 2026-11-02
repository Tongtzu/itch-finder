"""Score posts for pain, money and urgency signals."""
import math
import re
from collections.abc import Iterable

from itch_finder.models import Post, ScoredPost

PAIN_PATTERNS: dict[str, int] = {
    r"\bis there (a|an|any) (tool|app|way|software|template|script|service)\b": 3,
    r"\b(i|we) (hate|can't stand|cannot stand)\b": 2,
    r"\bstruggling (with|to)\b": 2,
    r"\bwast(e|es|ed|ing) (so much|hours|time|days)\b": 3,
    r"\bhow (do|can|would) (i|you|we)\b": 1,
    r"\bfrustrat(ed|ing)\b": 2,
    r"\bnightmare\b": 2,
    r"\bkeeps? (breaking|crashing|failing)\b": 2,
    r"\bmanual(ly)?\b": 1,
    r"\btedious\b": 2,
    r"\b(not working|doesn't work|does not work|stopped working)\b": 2,
    r"\bautomat(e|ically|ing)\b": 1,
    r"\bevery time\b": 1,
    r"\berror\b": 1,
}

MONEY_PATTERNS: dict[str, int] = {
    r"\b(would|willing to|happy to|happily|gladly) pay\b": 4,
    r"\btake my money\b": 4,
    r"\bhire (someone|a|an)\b": 3,
    r"\$\d+": 1,
    r"\b(client|customer)s?\b": 1,
    r"\bbudget\b": 1,
}

URGENCY_PATTERNS: dict[str, int] = {
    r"\b(asap|urgent(ly)?|deadline|tomorrow|tonight)\b": 3,
    r"\b(losing|lost) (money|clients|customers|sales|hours)\b": 3,
    r"\bevery (single )?(day|week|month)\b": 1,
    r"\bhelp\b": 1,
}

MONEY_WEIGHT = 1.5
UPVOTE_WEIGHT = 0.5


def _weigh(text: str, patterns: dict[str, int]) -> int:
    return sum(w for pat, w in patterns.items() if re.search(pat, text, re.IGNORECASE))


def score_post(post: Post) -> ScoredPost:
    text = post.text
    pain = _weigh(text, PAIN_PATTERNS)
    money = _weigh(text, MONEY_PATTERNS)
    urgency = _weigh(text, URGENCY_PATTERNS)
    if pain == 0:
        return ScoredPost(post=post, pain=0, money=money, urgency=urgency, total=0.0)
    engagement = math.log1p(max(post.comments, 0)) + UPVOTE_WEIGHT * math.log1p(max(post.upvotes, 0))
    total = pain + MONEY_WEIGHT * money + urgency + engagement
    return ScoredPost(post=post, pain=pain, money=money, urgency=urgency, total=round(total, 2))


def qualifying(posts: Iterable[Post], min_score: float) -> list[ScoredPost]:
    scored = (score_post(p) for p in posts)
    kept = [s for s in scored if s.pain > 0 and s.total >= min_score]
    return sorted(kept, key=lambda s: s.total, reverse=True)
