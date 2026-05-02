import os, re, json, hashlib, feedparser, requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).parent / ".env", override=True)

NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
SEEN_IDS_FILE           = Path(__file__).parent / ".seen_ids.json"
MAX_ARTICLES            = 20
NOTION_DIGEST_PARENT_ID = "55be7e22-aa16-4057-87fc-939a2ff1f79a"

FEEDS = [
    {"url": "https://www.cfodive.com/feeds/news/",                           "source": "CFO Dive",        "tier": "⭐ Mid"},
    {"url": "https://www.fintechweekly.com/feed",                            "source": "FinTech Weekly",  "tier": "📎 Niche"},
    {"url": "https://fintechfutures.com/feed/",                              "source": "FinTech Futures", "tier": "📎 Niche"},
    {"url": "https://feeds.feedburner.com/pymnts",                           "source": "PYMNTS",          "tier": "📎 Niche"},
    {"url": "https://www.bankingdive.com/feeds/news/",                       "source": "Banking Dive",    "tier": "⭐ Mid"},
    {"url": "https://venturebeat.com/category/ai/feed/",                     "source": "VentureBeat AI",  "tier": "🏆 Top"},
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "source": "TechCrunch AI",   "tier": "🏆 Top"},
    {"url": "https://www.axios.com/feeds/feed.rss",                          "source": "Axios",           "tier": "🏆 Top"},
    {"url": "https://news.sap.com/feed/",                                    "source": "SAP News",        "tier": "🏆 Top"},
    {"url": "https://news.crunchbase.com/feed/",                             "source": "Crunchbase News", "tier": "⭐ Mid"},
]

TOPIC_KEYWORDS = {
    "AI in FP&A": ["fp&a","financial planning","forecasting","budgeting ai","finance automation","cfo ai","finance operations","erp ai","workday ai","anaplan","adaptive insights"],
    "CFO & Finance Tools": ["cfo","finance tool","finance software","accounting ai","expense management","accounts payable","treasury ai","financial close","reporting automation","cashflow ai","brex","ramp"],
    "Fintech & AI Startups": ["fintech startup","fintech funding","series a fintech","ai startup finance","embedded finance","b2b fintech","raises","seed round fintech"],
    "AI in Banking": ["ai banking","bank ai","generative ai bank","llm financial","credit ai","risk ai","fraud detection ai","compliance ai"],
}

RELEVANCE_KEYWORDS = {
    "🔥 High": ["fp&a","cfo","financial planning","finance automation","fintech ai","ai adoption finance","enterprise finance ai"],
    "👀 Worth Reading": ["ai finance","banking ai","financial services ai","generative ai finance","llm finance"],
}

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&rsquo;',"'").replace('&lsquo;',"'").replace('&ldquo;','"').replace('&rdquo;','"').replace('&amp;','&').replace('&nbsp;',' ')
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
    ai_terms = [r"\bai\b", r"\bllm\b", r"\bgpt\b", "artificial intelligence", "machine learning",
                "generative ai", "copilot", "chatgpt"]
    finance_terms = ["finance","fintech","banking","cfo","fp&a","financial","accounting","treasury","investment","payment","lending","credit","workday","erp","enterprise software","saas","oracle","sap"]
    exclude_terms = ["military","warfare","iran","israel","ukraine","russia","congress","senate","election","celebrity","sports","nfl","nba","hormuz","blockade"]
    if any(ex in text_lower for ex in exclude_terms):
        return False
    has_ai = any(re.search(t, text_lower) for t in ai_terms)
    has_finance = any(t in text_lower for t in finance_terms)
    return has_ai and has_finance

def fetch_articles(seen_ids):
    articles = []
    for feed_config in FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            for entry in feed.entries[:10]:
                url = entry.get("link", "")
                if not url: continue
                uid = article_id(url)
                if uid in seen_ids: continue
                title   = strip_html(entry.get("title", ""))
                summary = strip_html(entry.get("summary", entry.get("description", "")))
                if not is_finance_ai_related(f"{title} {summary}"): continue
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                date_str = datetime(*pub[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d") if pub else datetime.now().strftime("%Y-%m-%d")
                articles.append({"id":uid,"title":title,"summary":summary[:500],"url":url,"source":feed_config["source"],"tier":feed_config["tier"],"date":date_str,"topics":detect_topics(f"{title} {summary}"),"relevance":detect_relevance(f"{title} {summary}")})
        except Exception as e:
            print(f"  ⚠️  Failed {feed_config['source']}: {e}")
    priority = {"🔥 High":0,"👀 Worth Reading":1,"📌 FYI":2}
    articles.sort(key=lambda a: priority[a["relevance"]])
    return articles[:MAX_ARTICLES]

def ai_summarize(articles):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for article in articles:
        try:
            prompt = f"""Summarize this AI/fintech news article in 3-4 sentences of plain prose. No headers, no bold labels, no bullet points, no markdown formatting.

Article title: {article['title']}
Source: {article['source']}
Raw excerpt: {article['summary']}

Write flowing sentences that cover what happened (name the company, tool, or person), why it matters to finance teams, and one practical implication. Factual and concise."""
            msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=350, messages=[{"role":"user","content":prompt}])
            article["summary"] = msg.content[0].text.strip()
        except Exception as e:
            print(f"  ⚠️  Summarization failed for '{article['title']}': {e}")
    return articles

def push_daily_digest(articles):
    headers = {"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"}
    today = datetime.now().strftime("%B %-d, %Y")
    date_iso = datetime.now().strftime("%Y-%m-%d")
    blocks = []
    for a in articles:
        meta = f"{a['relevance']}  ·  {a['source']} {a['tier']}  ·  {', '.join(a['topics'])}"
        blocks += [
            {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":a["title"][:200],"link":{"url":a["url"]}}}]}},
            {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":meta},"annotations":{"italic":True,"color":"gray"}}]}},
            {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":a["summary"][:2000]}}]}},
            {"object":"block","type":"divider","divider":{}},
        ]
    payload = {
        "parent":     {"database_id": NOTION_DATABASE_ID},
        "icon":       {"emoji": "📅"},
        "properties": {
            "Title":    {"title":    [{"text": {"content": f"AI in Finance Digest — {today}"}}]},
            "Date":     {"date":     {"start": date_iso}},
            "Added By": {"select":   {"name": "Auto-Fetch"}},
        },
        "children": blocks,
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=30)
    if res.status_code == 200:
        page_url = res.json().get("url", "")
        print(f"  ✅ Digest page created: {page_url}")
        return page_url
    else:
        print(f"  ❌ Failed ({res.status_code}): {res.text[:300]}")
        return None

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
    page_url = push_daily_digest(articles)
    for a in articles:
        seen_ids.add(a["id"])
    save_seen_ids(seen_ids)
    print(f"\n✨ Done! {len(articles)} articles in today's digest.")
    if page_url:
        print(f"🔗 Share link: {page_url}")

if __name__ == "__main__":
    main()
