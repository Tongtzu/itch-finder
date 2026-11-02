"""Reply drafts for intercepted posts. You review and post them yourself, by hand."""

HEADER = """# Reply drafts ({today})

Post these yourself. Itch Finder never posts, comments or messages for you.

- **Answer the question fully**, so the reply helps even if they never buy anything.
- Only add the disclosure line where the community's rules allow self-promotion. Many don't.
- After posting, run the `replied` command under each draft so `status` can tell what converts.
"""

DISCLOSURE = ("Disclosure: I made {offer} for this exact problem, "
              "but the steps above are all you need.")


def template_reply(item: dict) -> str:
    return (f'[Answer "{item["title"]}" first: the concrete fix in 3-5 steps, '
            "with the exact formula or code.]\n"
            "[If their setup is unclear, ask one short question about it.]")


def _entry(item: dict, reply: str | None, offer: str | None) -> str:
    lines = [
        f"## [{item['title']}]({item['url']})",
        f"`{item['id']}` · {item['source']} · score {item['score']}",
        "",
        "```text",
        reply or template_reply(item),
        "```",
    ]
    if offer:
        lines += ["", "Optional, only where self-promotion is allowed:", "",
                  f"> {DISCLOSURE.format(offer=offer)}"]
    offer_flag = f' --offer "{offer}"' if offer else ""
    lines += ["", f"Posted it? `python -m itch_finder replied {item['id']}{offer_flag}`"]
    return "\n".join(lines)


def render(items: list[dict], replies: dict[str, str | None], offer: str | None,
           today: str) -> str:
    parts = [HEADER.format(today=today)]
    parts += [_entry(i, replies.get(i["id"]), offer) for i in items]
    return "\n\n".join(parts) + "\n"
