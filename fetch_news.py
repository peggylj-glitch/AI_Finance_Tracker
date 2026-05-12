import os, re, json, hashlib, feedparser, requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import anthropic
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YT_AVAILABLE = True
except ImportError:
    YT_AVAILABLE = False

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

YOUTUBE_CHANNELS = [
    {"channel_id": "UCcefcZRL2oaA_uBNeo5UOWg", "source": "Y Combinator",   "tier": "🏆 Top"},
    {"channel_id": "UC9cn0TuPq4dnbTY-CBsm8XA",  "source": "a16z",           "tier": "🏆 Top"},
    {"channel_id": "UCWrF0oN6unbXrWsTN7RctTw",  "source": "Sequoia Capital", "tier": "🏆 Top"},
    {"channel_id": "UCESLZhusAkFfsNsApnjF_Cg",  "source": "All-In Podcast", "tier": "🏆 Top"},
    {"channel_id": "UC-DRzaGnL_vtBUpCFH5M0tg",  "source": "TBPN",           "tier": "🏆 Top"},
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

STRICT_FINANCE_TERMS = [
    "finance","fintech","banking","cfo","fp&a","financial","accounting",
    "treasury","payment","lending","credit","investment","revenue","budget",
]

def is_finance_ai_related(title, summary):
    combined   = (title + " " + summary).lower()
    title_lower = title.lower()
    ai_terms = [r"\bai\b", r"\bllm\b", r"\bgpt\b", "artificial intelligence", "machine learning",
                "generative ai", "copilot", "chatgpt"]
    exclude_terms = [
        "military","warfare","iran","israel","ukraine","russia","congress","senate",
        "election","celebrity","sports","nfl","nba","hormuz","blockade",
        "starting a business","solopreneur","side hustle","job interview",
        "career advice","hiring tips","resume","dating","lifestyle",
        "media company","digital publisher","buzzfeed","controlling stake",
        "box office","streaming deal","record label","entertainment deal",
    ]
    if any(ex in combined for ex in exclude_terms):
        return False
    has_ai = any(re.search(t, combined) for t in ai_terms)
    if not has_ai:
        return False
    # Title must carry at least one finance term, OR the body has ≥3 distinct ones
    title_finance = sum(1 for t in STRICT_FINANCE_TERMS if t in title_lower)
    body_finance  = sum(1 for t in STRICT_FINANCE_TERMS if t in combined)
    return title_finance >= 1 or body_finance >= 3

def get_youtube_transcript(video_id, max_chars=3000):
    if not YT_AVAILABLE:
        return ""
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(s["text"] for s in segments)[:max_chars]
    except Exception:
        return ""

def fetch_rss_articles(seen_ids):
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
                if not is_finance_ai_related(title, summary): continue
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                date_str = datetime(*pub[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d") if pub else datetime.now().strftime("%Y-%m-%d")
                articles.append({"id":uid,"title":title,"summary":summary[:500],"url":url,"source":feed_config["source"],"tier":feed_config["tier"],"date":date_str,"topics":detect_topics(f"{title} {summary}"),"relevance":detect_relevance(f"{title} {summary}"),"type":"article"})
        except Exception as e:
            print(f"  ⚠️  Failed {feed_config['source']}: {e}")
    return articles

def fetch_youtube_articles(seen_ids):
    articles = []
    for ch in YOUTUBE_CHANNELS:
        try:
            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                url = entry.get("link", "")
                if not url: continue
                uid = article_id(url)
                if uid in seen_ids: continue
                title = strip_html(entry.get("title", ""))
                video_id = url.split("v=")[-1].split("&")[0]
                transcript = get_youtube_transcript(video_id)
                description = strip_html(entry.get("summary", ""))
                content = transcript or description
                if not is_finance_ai_related(title, content): continue
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                date_str = datetime(*pub[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d") if pub else datetime.now().strftime("%Y-%m-%d")
                articles.append({"id":uid,"title":title,"summary":content[:2000],"url":url,"source":ch["source"],"tier":ch["tier"],"date":date_str,"topics":detect_topics(f"{title} {content}"),"relevance":detect_relevance(f"{title} {content}"),"type":"video"})
        except Exception as e:
            print(f"  ⚠️  Failed {ch['source']}: {e}")
    return articles

def fetch_articles(seen_ids):
    articles = fetch_rss_articles(seen_ids) + fetch_youtube_articles(seen_ids)
    priority = {"🔥 High":0,"👀 Worth Reading":1,"📌 FYI":2}
    articles.sort(key=lambda a: priority[a["relevance"]])
    # Keep at most 1 item per source (best relevance already at top after sort)
    seen_sources = set()
    deduped = []
    for a in articles:
        if a["source"] not in seen_sources:
            deduped.append(a)
            seen_sources.add(a["source"])
    return deduped[:MAX_ARTICLES]

def ai_summarize(articles):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for article in articles:
        try:
            if len(article["summary"]) <= 80:
                continue
            is_video = article.get("type") == "video"
            content_label = "Transcript excerpt" if is_video else "Excerpt"
            source_type = "video/podcast episode" if is_video else "article"
            prompt = f"""Write a 2-3 sentence factual summary of this {source_type} for a senior FP&A leader. Plain prose only — no headers, bullets, or markdown.

Title: {article['title']}
Source: {article['source']}
{content_label}: {article['summary']}

State what was discussed and who is involved. Stick to the facts — no interpretation, no "this is relevant because" framing."""
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
        type_badge = "📹 " if a.get("type") == "video" else ""
        meta = f"{a['relevance']}  ·  {type_badge}{a['source']} {a['tier']}  ·  {', '.join(a['topics'])}"
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
    print("\n📡 Fetching from RSS feeds and YouTube...")
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
