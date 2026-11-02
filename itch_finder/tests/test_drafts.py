from itch_finder import drafts

ITEM = {"id": "hn:1", "source": "hn", "url": "https://x/1", "title": "VBA macro keeps crashing",
        "body": "help", "score": 7.5, "status": "new"}


def test_render_lists_item_with_template_and_replied_command():
    md = drafts.render([ITEM], {}, offer=None, today="2026-11-02")
    assert "[VBA macro keeps crashing](https://x/1)" in md
    assert "VBA macro keeps crashing" in drafts.template_reply(ITEM)
    assert "python -m itch_finder replied hn:1" in md
    assert "Disclosure" not in md


def test_render_uses_ai_reply_and_disclosed_offer_line():
    md = drafts.render([ITEM], {"hn:1": "Wrap the loop in DoEvents."}, offer="VBA Fix Kit",
                       today="2026-11-02")
    assert "Wrap the loop in DoEvents." in md
    assert "Disclosure: I made VBA Fix Kit" in md
    assert '--offer "VBA Fix Kit"' in md
