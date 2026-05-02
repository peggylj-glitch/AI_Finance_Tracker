# AI in Finance — Daily News Tracker
## Project Context for Claude Code

### What this project does
A Python script that pulls AI/finance news from RSS feeds, filters for relevance,
summarizes each article using Claude (Haiku), and pushes to a Notion database daily.

### Current status
- ✅ Notion database created and working (articles push successfully)
- ✅ RSS fetching working (finds ~6 articles per run)
- ❌ fetch_news.py on user's Mac is CORRUPTED — a failed `curl` command overwrote it with "400: Invalid request"
- ❌ HTML stripping fix not yet applied (summaries show raw `<figure><div><img...` tags)

### The primary task
Replace the corrupted `fetch_news.py` on the user's Mac with the correct working version.
The correct file is below in full. Write it to: `~/Projects/AI_finance_tracker/fetch_news.py`

---

## Correct fetch_news.py (full file)

```python
import os, re, json, hashlib, feedparser, requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()

NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
SEEN_IDS_FILE      = Path(__file__).parent / ".seen_ids.json"
MAX_ARTICLES       = 20

FEEDS = [
    {"url": "https://www.cfodive.com/feeds/news/",                           "source": "CFO Dive"},
    {"url": "https://www.fintechweekly.com/feed",                            "source": "FinTech Weekly"},
    {"url": "https://fintechfutures.com/feed/",                              "source": "FinTech Futures"},
    {"url": "https://feeds.feedburner.com/pymnts",                           "source": "PYMNTS"},
    {"url": "https://www.bankingdive.com/feeds/news/",                       "source": "Banking Dive"},
    {"url": "https://venturebeat.com/category/ai/feed/",                     "source": "VentureBeat AI"},
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "source": "TechCrunch AI"},
    {"url": "https://www.axios.com/feeds/feed.rss",                          "source": "Axios"},
    {"url": "https://a16z.com/feed/",                                        "source": "a16z"},
    {"url": "https://news.crunchbase.com/feed/",                             "source": "Crunchbase News"},
]

TOPIC_KEYWORDS = {
    "AI in FP&A": [
        "fp&a","financial planning","forecasting","budgeting ai","finance automation",
        "cfo ai","finance operations","erp ai","workday ai","anaplan","adaptive insights"
    ],
    "CFO & Finance Tools": [
        "cfo","finance tool","finance software","accounting ai","expense management",
        "accounts payable","treasury ai","financial close","reporting automation",
        "cashflow ai","brex","ramp"
    ],
    "Fintech & AI Startups": [
        "fintech startup","fintech funding","series a fintech","ai startup finance",
        "embedded finance","b2b fintech","raises","seed round fintech"
    ],
    "AI in Banking": [
        "ai banking","bank ai","generative ai bank","llm financial",
        "credit ai","risk ai","fraud detection ai","compliance ai"
    ],
}

RELEVANCE_KEYWORDS = {
    "🔥 High": [
        "fp&a","cfo","financial planning","finance automation",
        "fintech ai","ai adoption finance","enterprise finance ai"
    ],
    "👀 Worth Reading": [
        "ai finance","banking ai","financial services ai",
        "generative ai finance","llm finance"
    ],
}

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = (text.replace('&rsquo;', "'").replace('&lsquo;', "'")
                .replace('&ldquo;', '"').replace('&rdquo;', '"')
                .replace('&amp;', '&').replace('&nbsp;', ' '))
    return re.sub(r'\s+', ' ', text).strip()

def load_seen_ids():
    if SEEN_IDS_FILE.exists():
        return set(json.loads(SEEN_IDS_FILE.read_text()))
    return set()

def save_seen_ids(seen):
    SEEN_IDS_FILE.write_text(json.dumps(list(seen)))

def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()

def detect_topics(text):
    text_lower = text.lower()
    matched = [t for t, kws in TOPIC_KEYWORDS.items() if any(kw in text_lower for kw in kws)]
    return matched or ["AI in Banking"]

def detect_relevance(text):
    text_lower = text.lower()
    for level, kws in RELEVANCE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return level
    return "📌 FYI"

def is_finance_ai_related(text):
    text_lower = text.lower()
    ai_terms    = ["ai","artificial intelligence","machine learning","llm","generative","automation","gpt"]
    finance_terms = ["finance","fintech","banking","cfo","fp&a","financial","accounting",
                     "treasury","investment","payment","lending","credit"]
    exclude_terms = ["military","warfare","iran","israel","ukraine","russia",
                     "congress","senate","election","celebrity","sports","nfl","nba",
                     "hormuz","blockade"]
    if any(ex in text_lower for ex in exclude_terms):
        return False
    return any(t in text_lower for t in ai_terms) and any(t in text_lower for t in finance_terms)

def fetch_articles(seen_ids):
    articles = []
    for feed_config in FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            for entry in feed.entries[:10]:
                url = entry.get("link", "")
                if not url:
                    continue
                uid = article_id(url)
                if uid in seen_ids:
                    continue
                title   = strip_html(entry.get("title", ""))
                summary = strip_html(entry.get("summary", entry.get("description", "")))
                if not is_finance_ai_related(f"{title} {summary}"):
                    continue
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                date_str = datetime(*pub[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d") if pub else datetime.now().strftime("%Y-%m-%d")
                articles.append({
                    "id":        uid,
                    "title":     title,
                    "summary":   summary[:500],
                    "url":       url,
                    "source":    feed_config["source"],
                    "date":      date_str,
                    "topics":    detect_topics(f"{title} {summary}"),
                    "relevance": detect_relevance(f"{title} {summary}"),
                })
        except Exception as e:
            print(f"  ⚠️  Failed {feed_config['source']}: {e}")
    priority = {"🔥 High": 0, "👀 Worth Reading": 1, "📌 FYI": 2}
    articles.sort(key=lambda a: priority[a["relevance"]])
    return articles[:MAX_ARTICLES]

def ai_summarize(articles):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for article in articles:
        try:
            prompt = f"""You are summarizing AI/fintech news for a senior FP&A leader at a US nonprofit school network.

Article title: {article['title']}
Source: {article['source']}
Raw excerpt: {article['summary']}

Write a 3-4 sentence digest covering:
1. What happened (be specific — name the company, tool, or person)
2. Why it matters to finance teams or CFOs
3. A practical implication — tool to watch, trend to flag, or risk to note

Be direct and specific. No fluff."""
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            article["summary"] = msg.content[0].text.strip()
        except Exception as e:
            print(f"  ⚠️  Summarization failed for '{article['title']}': {e}")
    return articles

def push_to_notion(articles):
    headers = {
        "Authorization":  f"Bearer {NOTION_TOKEN}",
        "Content-Type":   "application/json",
        "Notion-Version": "2022-06-28",
    }
    pushed = 0
    for a in articles:
        payload = {
            "parent":     {"database_id": NOTION_DATABASE_ID},
            "icon":       {"emoji": "📰"},
            "properties": {
                "Title":    {"title":       [{"text": {"content": a["title"][:200]}}]},
                "Date":     {"date":        {"start": a["date"]}},
                "Topic":    {"multi_select": [{"name": t} for t in a["topics"]]},
                "Source":   {"rich_text":   [{"text": {"content": a["source"]}}]},
                "Summary":  {"rich_text":   [{"text": {"content": a["summary"][:2000]}}]},
                "URL":      {"url":         a["url"]},
                "Relevance":{"select":      {"name": a["relevance"]}},
                "Added By": {"select":      {"name": "Auto-Fetch"}},
            },
        }
        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers, json=payload, timeout=15
        )
        if res.status_code == 200:
            pushed += 1
            print(f"  ✅ {a['source']} — {a['title'][:70]}")
        else:
            print(f"  ❌ Failed ({res.status_code}): {a['title'][:60]}\n     {res.text[:200]}")
    return pushed

def main():
    print(f"\n🤖 AI in Finance Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 60)
    seen_ids = load_seen_ids()
    print(f"📋 Known articles: {len(seen_ids)}")
    print("\n📡 Fetching from RSS feeds...")
    articles = fetch_articles(seen_ids)
    print(f"   Found {len(articles)} new relevant articles")
    if not articles:
        print("   Nothing new today. Check back tomorrow!")
        return
    print("\n🧠 Summarizing with Claude...")
    articles = ai_summarize(articles)
    print(f"\n📬 Pushing to Notion...")
    pushed = push_to_notion(articles)
    for a in articles:
        seen_ids.add(a["id"])
    save_seen_ids(seen_ids)
    print(f"\n✨ Done! {pushed}/{len(articles)} articles added to Notion.")

if __name__ == "__main__":
    main()
```

---

## Environment variables (.env file)
Location: `~/Projects/AI_finance_tracker/.env`

```
ANTHROPIC_API_KEY=<user's key — do not store here, ask user to confirm>
NOTION_TOKEN=<user's Notion integration token>
NOTION_DATABASE_ID=ea5ba05ed2574aa8ad19a3df66730b95
```

## Notion database
- Name: 📰 AI in Finance — Daily News Tracker
- Database ID: ea5ba05ed2574aa8ad19a3df66730b95
- Location: Reading List page in user's Notion workspace
- Views: Default table, 🔥 By Relevance (board), 📊 FP&A Focus (table filtered to AI in FP&A)

## Project folder on user's Mac
`~/Projects/AI_finance_tracker/`

Files:
- `fetch_news.py` — CORRUPTED, needs replacing with the code above
- `.env` — contains API keys (working Notion token + Anthropic key)
- `.env.example` — template
- `README.md` — setup instructions
- `.github/workflows/daily_fetch.yml` — GitHub Actions for daily automation

## How to fix immediately in Claude Code
1. Write the correct `fetch_news.py` content above to `~/Projects/AI_finance_tracker/fetch_news.py`
2. Run: `python3 ~/Projects/AI_finance_tracker/fetch_news.py`
3. Verify clean summaries appear in Notion (no HTML tags)

## Known issues resolved
- Notion 401: Fixed (user regenerated token and reconnected integration)
- Anthropic credits: Fixed ($5 loaded, key confirmed working — "Last used at: Mar 23, 2026")
- HTML in summaries: Fix is IN the correct fetch_news.py above (strip_html function) but not yet on disk
- Off-topic articles (geopolitics): Fixed via exclude_terms list in is_finance_ai_related()
