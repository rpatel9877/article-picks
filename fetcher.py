"""Opens each link, pulls out the readable article text, and checks for a paywall."""
import io
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import trafilatura

# Sites that require a subscription for most articles. Editable extras live in Settings.
PAYWALL_DOMAINS = {
    "wsj.com", "ft.com", "bloomberg.com", "barrons.com", "economist.com", "nytimes.com",
    "washingtonpost.com", "marketwatch.com", "investors.com", "newyorker.com",
    "theatlantic.com", "wired.com", "hbr.org", "foreignaffairs.com", "foreignpolicy.com",
    "institutionalinvestor.com", "risk.net", "thetimes.co.uk", "telegraph.co.uk",
    "latimes.com", "bostonglobe.com", "businessinsider.com", "fortune.com",
    "theinformation.com", "puck.news", "thediplomat.com", "nikkei.com", "asia.nikkei.com",
    "handelsblatt.com", "scmp.com", "globeandmail.com", "afr.com", "morningstar.com/premium",
}

PAYWALL_PHRASES = (
    "subscribe to continue", "subscribers only", "to continue reading", "already a subscriber",
    "subscribe to read", "this article is for subscribers", "sign in to continue reading",
    "create a free account to continue", "for full access", "subscribe now to read",
    "exclusive to subscribers", "become a member to read", "unlock this article",
)

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "smid", "cmpid", "ref", "sref", "srnd",
                   "guccounter", "share", "sh", "src", "mod", "ncid", "taid"}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MATH_PATTERN = re.compile(r"[=∑∫∂√±≈≤≥∞∏]|\\frac|\\sum|\b(?:alpha|beta|sigma|lambda|epsilon)\b", re.I)


# ---------- URL helpers ----------
def normalize_url(url):
    """Cleans tracking junk so the same article submitted twice is recognized as one."""
    url = (url or "").strip().strip("<>\"'")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not (k.lower().startswith("utm_") or k.lower() in TRACKING_PARAMS)]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def is_valid_url(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = parts.netloc.split(":")[0]
    return parts.scheme in ("http", "https") and "." in host and " " not in url and len(url) < 2000


def domain_of(url):
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def known_paywall(url, extra_domains=()):
    domain = domain_of(url)
    full = domain + urlsplit(url).path.lower()
    for d in list(PAYWALL_DOMAINS) + [e.strip().lower() for e in extra_domains if e.strip()]:
        d = d[4:] if d.startswith("www.") else d
        if "/" in d:
            if full.startswith(d):
                return d
        elif domain == d or domain.endswith("." + d):
            return d
    return None


# ---------- text stats ----------
def _syllables(word):
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups) - (1 if word.endswith("e") and len(groups) > 1 else 0)
    return max(count, 1)


def reading_ease(text):
    """Flesch reading ease: 60+ is plain English, under 30 is academic."""
    words = re.findall(r"[A-Za-z']+", text)
    sentences = max(len(re.findall(r"[.!?]+(?:\s|$)", text)), 1)
    if len(words) < 50:
        return None
    syllables = sum(_syllables(w) for w in words)
    return round(206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words)), 1)


def math_density(text, word_count):
    if not word_count:
        return 0.0
    return round(len(MATH_PATTERN.findall(text)) / word_count * 1000, 1)


# ---------- main entry point ----------
def fetch_article(url, extra_paywall_domains=(), timeout=20):
    info = {
        "url": url, "domain": domain_of(url), "title": "", "site": "", "author": "",
        "published": "", "text": "", "word_count": 0, "paywall": "free", "paywall_reason": "",
        "fetched": False, "error": "", "is_pdf": False, "reading_ease": None, "math_density": 0.0,
    }
    paywall_domain = known_paywall(url, extra_paywall_domains)
    status, html = None, ""

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        status = resp.status_code
        info["url_final"] = resp.url
        ctype = resp.headers.get("Content-Type", "").lower()
        if status >= 400:
            info["error"] = f"The site returned an error (HTTP {status})"
        elif "pdf" in ctype or resp.url.lower().endswith(".pdf"):
            info["is_pdf"] = True
            info.update(_read_pdf(resp.content, url))
            info["fetched"] = bool(info["text"])
        else:
            html = resp.text
            info.update(_read_html(html, url))
            info["fetched"] = bool(info["text"])
    except requests.RequestException as exc:
        info["error"] = f"Couldn't reach the site ({type(exc).__name__})"

    text = info["text"]
    info["word_count"] = len(re.findall(r"\b\w+\b", text))
    info["reading_ease"] = reading_ease(text) if text else None
    info["math_density"] = math_density(text, info["word_count"])

    # Paywall decision, strongest evidence first
    lower_html = html.lower()
    if paywall_domain:
        info["paywall"], info["paywall_reason"] = "likely", f"Subscription site ({paywall_domain})"
    elif status in (401, 402):
        info["paywall"], info["paywall_reason"] = "likely", "Site requires a login or payment"
    elif re.search(r'"isaccessibleforfree"\s*:\s*"?false', lower_html):
        info["paywall"], info["paywall_reason"] = "likely", "Page marks itself as subscriber-only"
    elif any(p in lower_html for p in PAYWALL_PHRASES) and info["word_count"] < 500:
        info["paywall"], info["paywall_reason"] = "likely", "Only a preview is readable"
    elif status in (403, 429):
        info["paywall"], info["paywall_reason"] = "unknown", "Site blocked automated reading"
    elif info["fetched"] and info["word_count"] < 120:
        info["paywall"], info["paywall_reason"] = "unknown", "Very little readable text"
    elif not info["fetched"]:
        info["paywall"], info["paywall_reason"] = "unknown", "Page couldn't be read"
    return info


def _read_html(html, url):
    out = {"title": "", "site": "", "author": "", "published": "", "text": ""}
    try:
        raw = trafilatura.extract(html, url=url, output_format="json", with_metadata=True,
                                  include_comments=False, include_tables=False)
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    out["text"] = (data.get("text") or "").strip()
    out["title"] = (data.get("title") or "").strip()
    out["site"] = (data.get("sitename") or "").strip()
    out["author"] = (data.get("author") or "").strip()
    out["published"] = (data.get("date") or "").strip()
    if not out["title"]:
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I) \
            or re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


def _read_pdf(content, url):
    out = {"title": "", "site": "", "author": "", "published": "", "text": ""}
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = [p.extract_text() or "" for p in reader.pages[:25]]
        out["text"] = "\n".join(pages).strip()
        meta = reader.metadata or {}
        out["title"] = (getattr(meta, "title", None) or "").strip()
    except Exception:
        pass
    if not out["title"]:
        out["title"] = urlsplit(url).path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
    return out
