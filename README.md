# Itch Finder

A small, **read-only** research CLI. It searches recent public posts on Reddit, Hacker News and
Stack Exchange for problems people keep running into ("is there a tool…", "I'd pay for…",
"wasting hours on…"), scores them for pain, buying intent and urgency, groups them by topic, and
writes a markdown report so you can decide which problems are worth solving.

It covers the whole loop for one person with no audience:

1. **Mine** recurring pain into topics, each with a 3-tier offer stack (`mine`).
2. **Intercept** fresh posts where someone is asking for help right now (`intercept`).
3. **Draft** replies you review and post yourself, by hand (`drafts`, `replied`).
4. **Sell** under a brand name with ready-to-paste store listings (`mine --brand`).
5. **Replicate what converts**: sales and replies per offer and source show what to copy (`status`).

## What it never does

- It never posts, comments, votes or sends messages on any platform.
- It never stores usernames. It keeps only post titles, post text, scores and links.
- It doesn't train AI models on platform content.
- It stays within rate limits: requests are spaced out, and it stops at the first 401/403/429 response.

## Install

```bash
pip install -r requirements.txt
```

Requires Python 3.10+.

## Usage

```bash
# Hacker News + Stack Overflow only (no keys needed)
python -m itch_finder mine --niche excel --se-sites stackoverflow

# Add subreddits (needs Reddit app keys, see below)
python -m itch_finder mine --niche excel --subs excel,smallbusiness --days 90
```

The report goes to `itch_reports/<niche>-<date>.md`. For each topic it lists the evidence posts
(with links) and a three-tier offer idea: a quick-fix kit, a toolkit and a done-for-you service.

Optional: add `--llm` and set `OPENROUTER_API_KEY` to get a short AI-written product angle for each topic.

Add `--brand "Sheet Rescue"` to also write `itch_listings/<niche>-<date>.md`: one product page per
offer, ready to paste into Gumroad, Lemon Squeezy or Payhip under that brand name. Only list what
you can deliver, and keep the refund line to what you will honour.

### Mining job ads (pasted by hand)

Job boards such as SEEK forbid scrapers and bots, so Itch Finder never fetches them. Copy the ads
yourself into a text file, separated by a line of `---` (a copied SEEK results page also works; it
splits on the "Listed … ago" lines), then:

```bash
python -m itch_finder jobs ads.txt --niche "ai engineer"
```

It writes `itch_reports/jobs-<niche>-<date>.md`. The report shows:

- **Needs:** how many ads ask for each need (AI agents, RAG, Azure/Copilot, governance and so on),
  and whether each one can be delivered as a remote product or needs a hire.
- **Hiring-only requirements:** clearances, office days and permanent roles.
- **Recurring terms** across the ads.
- **Draft offers** for the top deliverable need.

Recruiter names ("Recruited by …") are dropped.

### Intercepting demand

```bash
# Queue posts from the last 48 hours where someone is asking for help
python -m itch_finder intercept --niche excel --subs excel,smallbusiness

# Keep checking every 30 minutes (minimum 10); Ctrl+C stops
python -m itch_finder intercept --niche excel --subs excel --every 30

# Write reply drafts for everything new (add --llm for AI-written answers)
python -m itch_finder drafts --offer "Sheet Rescue"
```

Drafts go to `itch_drafts/<timestamp>.md`. Each one answers the question first. If you pass
`--offer`, it adds an optional, clearly labelled disclosure line; use it only where the community's
rules allow self-promotion. **You post every reply yourself.** After posting, mark it so `status`
can link replies to sales:

```bash
python -m itch_finder replied reddit:abc123 --offer "Sheet Rescue"
python -m itch_finder skip hn:456   # not worth answering
```

The queue is saved locally in `itch_queue.json` (titles, the first 600 characters of each post,
scores and links; no usernames).

### Tracking what converts

```bash
python -m itch_finder launch "Sheet Rescue"
python -m itch_finder sale "Sheet Rescue" 49 --source reddit
python -m itch_finder status
```

`status` shows revenue, SCALE / WATCH / KILL for each offer, and sales, replies and reply-to-sale
rate per offer and source, plus which pair to replicate next. Sales are saved locally in
`itch_finder_ledger.json`.

## Reddit access

Create a **script** app at <https://www.reddit.com/prefs/apps>, then add the keys to a `.env` file:

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

Itch Finder uses app-only OAuth (`client_credentials`) with read-only search requests.

## Tests

```bash
pip install pytest
python -m pytest itch_finder/tests -q
```

## License

MIT
