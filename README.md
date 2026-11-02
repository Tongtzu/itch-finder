# Itch Finder

A small, **read-only** research CLI. It searches recent public posts on Reddit, Hacker News and
Stack Exchange for problems people keep running into ("is there a tool…", "I'd pay for…",
"wasting hours on…"), scores them for pain, buying intent and urgency, groups them by topic, and
writes a markdown report so you can decide which problems are worth solving.

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

### Tracking what you launch

```bash
python -m itch_finder launch "Sheet Rescue"
python -m itch_finder sale "Sheet Rescue" 49
python -m itch_finder status   # revenue, plus SCALE / WATCH / KILL for each offer
```

Sales are saved locally in `itch_finder_ledger.json`.

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
