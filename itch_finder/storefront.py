"""Faceless storefront copy: one product page per offer, sold under a brand name."""
from itch_finder.models import Offer

DELIVERY = {
    "tripwire": "Instant download after purchase.",
    "core": "Instant download after purchase, walkthrough video included.",
    "done-for-you": "Send your file after purchase; you get it back fixed within 48 hours.",
}

HEADER = """# Store listings: {niche} ({today})

Paste each block into a free Gumroad / Lemon Squeezy / Payhip product page under the brand
**{brand}**. No face or real name needed.

Before publishing:
- Only list what you can deliver today. Build the kit before selling it, or start with done-for-you.
- No income claims and no made-up reviews. Add testimonials only from real buyers, with permission.
- Make sure the refund line matches what you will actually honour.
"""


def listing(offer: Offer, brand: str, keyword: str, niche: str) -> str:
    return "\n".join([
        f"## {offer.name} — ${offer.price}",
        f"*by {brand}*",
        "",
        offer.pitch,
        "",
        f"**Who it's for:** {niche} users who keep running into {keyword} problems.",
        f"**What you get:** {offer.deliverable}.",
        f"**Delivery:** {DELIVERY.get(offer.tier, 'Details sent after purchase.')}",
        "**Refunds:** If it doesn't solve your problem, reply within 14 days for a full refund.",
    ])


def render_listings(brand: str, niche: str, today: str,
                    stacks: dict[str, tuple[Offer, ...]]) -> str:
    parts = [HEADER.format(niche=niche, today=today, brand=brand)]
    parts += [listing(o, brand, kw, niche) for kw, stack in stacks.items() for o in stack]
    return "\n\n".join(parts) + "\n"
