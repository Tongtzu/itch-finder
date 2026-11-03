"""Optional: ask an LLM (via OpenRouter) for product angles and reply drafts."""
import logging
import os

from itch_finder.models import Cluster

log = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.0-flash-001"
EVIDENCE_LIMIT = 8
# Reddit's Responsible Builder Policy bars sharing its data or using it to train models, so
# Reddit text is never sent to a third-party LLM.
NO_AI_SOURCES = frozenset({"reddit"})
MAX_TOKENS = 300
TIMEOUT_S = 30

PROMPT = """These are real public complaints about "{kw}" from people in the {niche} space:
{evidence}

Reply in 3 short lines:
1. Core problem (one sentence, in their words)
2. Micro-product that solves it, buildable in 48h, priced under $50
3. A headline of six words or fewer
No hype and no income claims."""

REPLY_PROMPT = """Someone asked this in a public {niche} community:
Title: {title}
Text: {body}

Write a reply that actually solves it: concrete steps, plus the exact formula or code if relevant.
Under 150 words. No links, no product mentions, no greeting. If key details are missing, give the
most likely fix and ask one short question."""


def _complete(prompt: str, what: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        log.warning("OPENROUTER_API_KEY not set; skipping AI %s", what)
        return None
    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai package not installed; skipping AI %s", what)
        return None
    try:
        client = OpenAI(api_key=key, base_url=OPENROUTER_BASE, timeout=TIMEOUT_S)
        resp = client.chat.completions.create(
            model=os.environ.get("PAIN_MINER_MODEL", DEFAULT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
        )
    except Exception as exc:  # any API/network failure should only drop this one output
        log.warning("LLM %s failed: %s", what, exc)
        return None
    return (resp.choices[0].message.content or "").strip() or None


def angle_for(cluster: Cluster, niche: str) -> str | None:
    shareable = [s for s in cluster.posts if s.post.source not in NO_AI_SOURCES]
    if not shareable:
        log.info("No AI angle for %s: its evidence is all from Reddit", cluster.keyword)
        return None
    evidence = "\n".join(f"- {s.post.title[:200]}" for s in shareable[:EVIDENCE_LIMIT])
    return _complete(PROMPT.format(kw=cluster.keyword, niche=niche, evidence=evidence),
                     f"angle for {cluster.keyword}")


def reply_for(item: dict, niche: str) -> str | None:
    if item.get("source") in NO_AI_SOURCES:
        log.info("No AI reply for %s: Reddit text is not sent to an LLM", item["id"])
        return None
    return _complete(REPLY_PROMPT.format(niche=niche, title=item["title"], body=item["body"]),
                     f"reply for {item['id']}")
