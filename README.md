# 📰 AI in Finance — Daily News Tracker

Lightweight Python script that pulls AI/finance news from curated RSS feeds,
filters for relevance, summarizes each article with Claude, and pushes it to Notion daily.

Built for: FP&A leaders, CFOs, and finance teams tracking AI adoption in their industry.

---

## What It Tracks

| Topic | Example Coverage |
|---|---|
| **AI in FP&A** | AI-powered forecasting, budgeting tools, planning platforms (Anaplan, Adaptive) |
| **CFO & Finance Tools** | Expense management, AP automation, treasury AI, financial close tools |
| **Fintech & AI Startups** | Funding rounds, new launches, B2B fintech with AI angle |
| **AI in Banking** | Credit AI, fraud detection, LLMs in financial services |

---

## Quick Setup (15 mins)

### 1. Clone or download this folder

```bash
git clone https://github.com/yourname/ai-finance-tracker
cd ai-finance-tracker
```

### 2. Install dependencies

```bash
pip install feedparser requests python-dotenv anthropic
```

### 3. Set up your Notion database

**Option A — Let Claude build it for you** (recommended):
> Ask Claude: "Create a Notion database called AI in Finance Daily News Tracker with these fields: Title (title), Date (date), Topic (multi-select), Source (text), Summary (text), URL (url), Relevance (select), Added By (select)"

**Option B — Manual**:
1. Create a new Notion database
2. Add these fields:
   - `Title` — Title
   - `Date` — Date
   - `Topic` — Multi-select: `AI in FP&A`, `CFO & Finance Tools`, `Fintech & AI Startups`, `AI in Banking`
   - `Source` — Text
   - `Summary` — Text
   - `URL` — URL
   - `Relevance` — Select: `🔥 High`, `👀 Worth Reading`, `📌 FYI`
   - `Added By` — Select: `Auto-Fetch`, `Manual`

3. Connect your Notion integration:
   - Go to https://www.notion.so/my-integrations → create integration → copy token
   - Open your database → ... menu → Connections → add your integration

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys
```

You need:
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com
- `NOTION_TOKEN` — from https://www.notion.so/my-integrations
- `NOTION_DATABASE_ID` — the long ID in your Notion database URL

### 5. Run it

```bash
python fetch_news.py
```

---

## Automate Daily (GitHub Actions)

The easiest no-infra automation:

1. Push this folder to a private GitHub repo
2. Add your three API keys as **Repository Secrets**:
   - Settings → Secrets → Actions → New secret
3. The workflow (`.github/workflows/daily_fetch.yml`) runs automatically at **7:30am ET on weekdays**
4. You can also trigger it manually from the Actions tab anytime

---

## Customize

**Add feeds** — edit the `FEEDS` list in `fetch_news.py`:
```python
{"url": "https://yourfeed.com/rss", "source": "Your Source"},
```

**Add keywords** — edit `TOPIC_KEYWORDS` or `RELEVANCE_KEYWORDS` to tune what gets flagged

**Change schedule** — edit the `cron` line in `.github/workflows/daily_fetch.yml`

---

## How It Works

```
RSS Feeds (11 sources)
       ↓
Filter: must mention AI + Finance
       ↓
Deduplicate (against .seen_ids.json cache)
       ↓
Claude summarizes each article (1 sentence, FP&A lens)
       ↓
Push to Notion with topic tags + relevance scores
```

---

## Tips for Notion Views

Once data is flowing, set up these Notion views:
- **Board** grouped by `Relevance` — see 🔥 High items first
- **Table** filtered by `Topic = AI in FP&A` — focused reading
- **Gallery** for a visual news feed feel
- **Filter by Date = Today** — for your morning brief

---

*Built with Claude + feedparser + Notion API*
