"""
utils/website_scraper.py
Scrapes a client's website, extracts key business content, and
auto-ingests it into their RAG knowledge base.

Flow:
  1. Fetch homepage + important sub-pages (About, Services, FAQ, Contact)
  2. Extract clean text (strip nav/footer/ads)
  3. Ask Claude to summarize key business facts
  4. Ingest the summary + raw content into RAG
  5. Return a summary dict for the client profile
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


# Pages we try to find and scrape (in order of priority)
PRIORITY_PATHS = [
    "/",
    "/about", "/about-us", "/about_us",
    "/services", "/our-services", "/what-we-do",
    "/products",
    "/faq", "/faqs",
    "/contact", "/contact-us",
    "/pricing",
    "/team",
]

MAX_PAGES   = 8       # scrape at most this many distinct pages
MAX_CHARS   = 80_000  # total chars fed to Claude summary
TIMEOUT     = 15      # seconds per page request


def _normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _extract_text(html: str) -> str:
    """Extract readable text from HTML, stripping boilerplate."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "iframe", "noscript", "svg", "form", "aside"]):
        tag.decompose()

    # Get text with some structure preserved
    lines = []
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "span", "div"]):
        text = elem.get_text(separator=" ", strip=True)
        if len(text) > 30:  # skip tiny fragments
            lines.append(text)

    # Deduplicate and rejoin
    seen = set()
    clean = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            clean.append(line)

    return "\n".join(clean)


def _find_internal_links(html: str, base_url: str) -> list[str]:
    """Find internal links that match our priority paths."""
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc
    found = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        full = urljoin(base_url, href)
        parsed = urlparse(full)

        # Only same-domain links
        if parsed.netloc != domain:
            continue

        path = parsed.path.lower().rstrip("/") or "/"
        for priority in PRIORITY_PATHS[1:]:   # skip "/"
            if path == priority or path.endswith(priority):
                url_clean = full.split("?")[0].split("#")[0]
                if url_clean not in found:
                    found.append(url_clean)
                    break

    return found


async def scrape_website(url: str) -> dict:
    """
    Scrape a website and return a dict with:
      - pages_scraped: list of URLs fetched
      - raw_text: combined extracted text
      - error: None or error message
    """
    url = _normalize_url(url)
    pages_text = {}
    errors = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=TIMEOUT,
        verify=False,  # some small business sites have cert issues
    ) as client:
        # Always fetch homepage first
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            pages_text[url] = _extract_text(resp.text)
            homepage_html = resp.text
        except Exception as e:
            return {"pages_scraped": [], "raw_text": "", "error": str(e)}

        # Find priority sub-pages from the homepage
        internal_links = _find_internal_links(homepage_html, url)

        # Fetch sub-pages (up to MAX_PAGES total)
        for link in internal_links:
            if len(pages_text) >= MAX_PAGES:
                break
            if link in pages_text:
                continue
            try:
                resp = await client.get(link)
                resp.raise_for_status()
                pages_text[link] = _extract_text(resp.text)
            except Exception as e:
                errors.append(f"{link}: {str(e)}")

    raw_text = "\n\n---\n\n".join(
        f"[Page: {p}]\n{t}" for p, t in pages_text.items()
    )

    return {
        "pages_scraped": list(pages_text.keys()),
        "raw_text": raw_text[:MAX_CHARS],
        "error": None,
    }


async def summarize_business(raw_text: str, business_name: str) -> dict:
    """
    Ask Claude to extract structured business facts from scraped text.
    Returns a dict with: niche, description, services, target_audience, location, unique_value_prop
    """
    import anthropic
    import json

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model  = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")

    prompt = f"""You are analyzing a business website to extract key facts for a marketing knowledge base.

Business Name: {business_name}

Website Content:
{raw_text[:15000]}

Extract the following information as a JSON object. Be concise and factual.
If something isn't mentioned, use null.

{{
  "niche": "1-3 word industry/niche (e.g. 'Travel Agency', 'Life Coach', 'SaaS', 'Restaurant')",
  "description": "2-3 sentence business description",
  "services": "Comma-separated list of main services or products",
  "target_audience": "Who are their customers (age, demographics, interests)",
  "location": "City, State or region if mentioned, else null",
  "unique_value_prop": "What makes this business unique or their main selling point"
}}

Return ONLY the JSON object, no explanation."""

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Extract JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"Claude summary error: {e}")

    # Fallback — empty
    return {
        "niche": None, "description": None, "services": None,
        "target_audience": None, "location": None, "unique_value_prop": None
    }


async def scrape_and_ingest(
    url: str,
    client_id: str,
    business_name: str,
    db_profile_id: str,
) -> dict:
    """
    Full pipeline:
      1. Scrape website
      2. Summarize with Claude
      3. Ingest into RAG
    Returns a result dict with status + extracted facts.
    """
    from agents.rag_system import RAGSystem

    result = {
        "success": False,
        "pages_scraped": [],
        "facts": {},
        "error": None,
    }

    # Step 1: Scrape
    print(f"[Scraper] Scraping {url} for client {client_id}...")
    scrape_result = await scrape_website(url)

    if scrape_result["error"]:
        result["error"] = f"Could not access website: {scrape_result['error']}"
        return result

    if not scrape_result["raw_text"]:
        result["error"] = "Website returned no readable content."
        return result

    result["pages_scraped"] = scrape_result["pages_scraped"]

    # Step 2: Summarize
    print(f"[Scraper] Summarizing content with Claude...")
    facts = await summarize_business(scrape_result["raw_text"], business_name)
    result["facts"] = facts

    # Step 3: Ingest into RAG (chunked to stay within embedding token limits)
    print(f"[Scraper] Ingesting into RAG for {client_id}...")
    rag = RAGSystem()
    _CHUNK = 4_000  # chars per chunk — safe for text-embedding-ada-002 (8191 token limit)

    raw = scrape_result["raw_text"]
    for i in range(0, len(raw), _CHUNK):
        chunk = raw[i:i + _CHUNK].strip()
        if not chunk:
            continue
        rag.add_knowledge(
            text=chunk,
            client_id=client_id,
            source=url,
            category="website",
            tags=["website", "onboarding", "auto_scraped"],
        )

    # Also ingest the structured summary as a separate knowledge entry
    if any(facts.values()):
        summary_text = f"""Business Profile for {business_name}:

Niche/Industry: {facts.get('niche', 'N/A')}
Description: {facts.get('description', 'N/A')}
Services/Products: {facts.get('services', 'N/A')}
Target Audience: {facts.get('target_audience', 'N/A')}
Location: {facts.get('location', 'N/A')}
Unique Value Proposition: {facts.get('unique_value_prop', 'N/A')}
Website: {url}"""

        rag.add_knowledge(
            text=summary_text,
            client_id=client_id,
            source="auto_summary",
            category="business_profile",
            tags=["profile", "onboarding", "summary"],
        )

    result["success"] = True
    print(f"[Scraper] Done! {len(result['pages_scraped'])} pages ingested for {client_id}.")
    return result
