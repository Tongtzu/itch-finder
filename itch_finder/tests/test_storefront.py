from itch_finder.models import Offer
from itch_finder.storefront import render_listings

KIT = Offer(tier="tripwire", name="Vba Fix Kit", price=19, deliverable="PDF checklist",
            build_time="2-4 hours", pitch="Stop fighting vba problems.")
DFY = Offer(tier="done-for-you", name="Vba Done-For-You Setup", price=197,
            deliverable="I fix it for you", build_time="1-3 hours", pitch="Send me your mess.")


def test_render_listings_has_brand_price_and_delivery_per_tier():
    md = render_listings("Sheet Rescue", "excel", "2026-11-02", {"vba": (KIT, DFY)})
    assert "## Vba Fix Kit — $19" in md
    assert "*by Sheet Rescue*" in md
    assert "PDF checklist" in md
    assert "Instant download" in md
    assert "within 48 hours" in md


def test_render_listings_makes_no_income_claims():
    md = render_listings("Sheet Rescue", "excel", "2026-11-02", {"vba": (KIT,)}).lower()
    for banned in ("guaranteed income", "make money", "passive income"):
        assert banned not in md
