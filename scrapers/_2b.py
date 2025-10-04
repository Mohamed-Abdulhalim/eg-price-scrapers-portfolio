#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2B smartphones scraper — resilient category resolver + proxy + Supabase

Why this version?
- 2B keeps changing category slugs (causing 404). We now auto-resolve the category URL
  from a list of known slugs and optionally by sniffing the homepage nav.
- Works on CI via requests-only (no Selenium). Supports sticky proxies (e.g., DataImpulse)
  through SCRAPER_PROXY env and excludes Supabase from proxy with NO_PROXY.
- Uploads to Supabase `products` using columns that exist in your table.

ENV expected (in GitHub Actions or locally):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY  (or SUPABASE_ANON_KEY as fallback)
  SUPABASE_TABLE=products    (optional)
  SCRAPER_PROXY=http://user:pass@gw.example.com:port (optional)
  NO_PROXY=.supabase.co,localhost,127.0.0.1         (recommended)

Run examples:
  python scrapers/_2b.py --lang ar --max-pages 8
  python scrapers/_2b.py --lang en --max-pages 5 --no-search

Notes for CI with a proxy:
- Set sticky session in your proxy dashboard and use the sticky endpoint/port.
- In workflow step set env SCRAPER_PROXY and NO_PROXY as shown in the workflow yaml.
"""
import os, re, time, csv, json, random, argparse
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

# ---------------- Defaults ----------------
DEFAULT_LANG = "en"               # crawl site root: en or ar
DEFAULT_MAX_PAGES = 10            # pagination depth for category and search
DEFAULT_OUT_CSV = "2b_smartphones.csv"
DEFAULT_OUT_JSON = "2b_smartphones.json"
DEFAULT_SEARCH_TERMS = [
    "iphone","apple","samsung","galaxy","xiaomi","redmi","poco","oppo","reno","realme",
    "huawei","honor","vivo","nokia","oneplus","motorola","infinix","tecno","sony",
    # Arabic safety nets
    "ايفون","ابل","سامسونج","شاومي","ريدمي","بوكو","اوبو","ريلمي","هواوي","هونر","فيفو","نوكيا","انفنيكس","تكنو","سوني",
]

# Known category slugs (2B rotates these sometimes)
CATEGORY_CANDIDATES = {
    "en": [
        "https://2b.com.eg/en/mobile-and-tablet/mobiles.html",
        "https://2b.com.eg/en/mobile-tablets/mobile-phones.html",
        "https://2b.com.eg/en/mobile-tablet/mobile-phones.html",
    ],
    "ar": [
        "https://2b.com.eg/ar/mobile-and-tablet/mobiles.html",
        "https://2b.com.eg/ar/mobile-tablets/mobile-phones.html",
        "https://2b.com.eg/ar/mobile-tablet/mobile-phones.html",
    ],
}

STORE = "2B"
COUNTRY = "EG"
CURRENCY = "EGP"

# Supabase client
try:
    from supabase import create_client
except Exception:
    create_client = None

# ---------------- HTTP/network hardening ----------------
UA_POOL = [
    # A few modern desktop agents
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def build_session(lang: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8" if lang == "ar" else "en-US,en;q=0.9,ar;q=0.4",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    })
    proxy = os.getenv("SCRAPER_PROXY")
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s


def _cf_warmup(session: requests.Session, lang: str):
    """Touch the language home once to set any cookies before real pages."""
    base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
    try:
        session.get(base, timeout=20)
        time.sleep(0.6 + random.random()*0.6)
    except Exception:
        pass


def fetch_html(session: requests.Session, url: str, lang: str, tries: int = 4) -> Optional[str]:
    """Fetch with retries, UA rotation, language flip on 403, and small jitter."""
    _cf_warmup(session, lang)
    for attempt in range(1, tries + 1):
        try:
            r = session.get(url, timeout=25, allow_redirects=True)
            if r.status_code == 403:
                # rotate UA and tweak language, then try alternate language path once
                session.headers.update({
                    "User-Agent": random.choice(UA_POOL),
                    "Accept-Language": ("ar,en-US;q=0.9,en;q=0.8" if lang == "ar" else "en-US,en;q=0.9,ar;q=0.4")
                })
                time.sleep(1.2 * attempt)
                if "/en/" in url:
                    alt = url.replace("/en/", "/ar/")
                    r = session.get(alt, timeout=25, allow_redirects=True)
                elif "/ar/" in url:
                    alt = url.replace("/ar/", "/en/")
                    r = session.get(alt, timeout=25, allow_redirects=True)
            if r.status_code in (520, 521, 522, 523, 524):  # Cloudflare oddities
                time.sleep(1.0 * attempt)
                continue
            r.raise_for_status()
            time.sleep(0.4 + random.random()*0.6)
            return r.text
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 404, 429, 503):
                time.sleep(0.8 * attempt)
                # do not loop forever on 404, just break so caller can handle
                if e.response.status_code == 404:
                    return None
                continue
            raise
        except requests.RequestException:
            time.sleep(0.8 * attempt)
            continue
    return None


def get_soup(session: requests.Session, url: str, lang: str) -> Optional[BeautifulSoup]:
    html = fetch_html(session, url, lang=lang)
    if not html:
        return None
    return BeautifulSoup(html, "html.parser")


# --------- Category URL resolver ---------

def resolve_category_via_candidates(session: requests.Session, lang: str) -> Optional[str]:
    for url in CATEGORY_CANDIDATES.get(lang, []):
        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                print(f"[2B] using category URL: {url}")
                return url
        except Exception:
            pass
    return None


def resolve_category_via_home_nav(session: requests.Session, lang: str) -> Optional[str]:
    base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
    soup = get_soup(session, base, lang)
    if not soup:
        return None
    anchors = soup.select("a[href]")
    # Targets to look for in link text
    if lang == "ar":
        targets = ["موبايل", "هواتف", "موبايلات"]
    else:
        targets = ["mobile", "mobiles", "phones", "mobile phones"]
    for a in anchors:
        text = (a.get_text(" ", strip=True) or "").lower()
        if any(t in text for t in targets):
            href = a.get("href")
            if href:
                if href.startswith("/"):
                    href = urljoin(base, href)
                # sanity check the destination
                try:
                    r = session.get(href, timeout=20, allow_redirects=True)
                    if r.status_code == 200 and ("mobile" in href or "phone" in href or "موبايل" in text):
                        print(f"[2B] discovered category URL from nav: {href}")
                        return href
                except Exception:
                    continue
    return None


def resolve_category_url(session: requests.Session, lang: str) -> Optional[str]:
    url = resolve_category_via_candidates(session, lang)
    if url:
        return url
    url = resolve_category_via_home_nav(session, lang)
    if url:
        return url
    print(f"[2B] No working category URL found for lang={lang}")
    return None


# ---------------- Parsing helpers ----------------
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_EN_MAP = {
    "ايفون": "iphone", "ابل": "apple", "برو ماكس": "Pro Max", "برو": "Pro", "ماكس": "Max",
    "بلس": "Plus", "الترا": "Ultra", "اير": "Air", "ميني": "Mini", "مينى": "Mini",
    "جيجا بايت": "GB", "جيجابايت": "GB", "رام": "RAM", "ثنائي الشريحة": "Dual SIM",
}

ACCESSORY_KILL = [
    "case","cover","screen","protector","glass","adapter","dock","charger","cable",
    "earbuds","earpods","airpods","headphone","pencil","stylus","band","watch","tag",
    # Arabic
    "جراب","حماية","كفر","شاحن","سماعة","سماعات","قلم","ساعة","تاج","حزام",
]

NOT_PHONE_SERIES = [
    "ipad","matepad","tab","tablet","playstation","ps5","macbook","laptop","notebook",
]

SMARTPHONE_HINTS = [
    "iphone","apple","samsung","galaxy","xiaomi","redmi","poco","oppo","reno","realme",
    "huawei","honor","vivo","nokia","oneplus","motorola","infinix","tecno","sony",
    "هاتف","موبايل","جوال","ايفون","سامسونج","شاومي","ريدمي","بوكو","اوبو","ريلمي","هواوي","هونر","فيفو","نوكيا","انفنيكس","تكنو","سوني"
]

SERIES_TO_BRAND = {"redmi": "xiaomi", "poco": "xiaomi", "galaxy": "samsung"}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def ar_to_en_tokens(text: str) -> str:
    t = text or ""
    for ar, en in AR_EN_MAP.items():
        t = re.sub(ar, en, t, flags=re.IGNORECASE)
    return t


def normalize_for_parse(raw: str) -> str:
    t = (raw or "").translate(ARABIC_DIGITS)
    t = ar_to_en_tokens(t)
    t = t.replace("–","-").replace("—","-")
    return normalize_spaces(t)


def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    t = text.translate(ARABIC_DIGITS)
    t = re.sub(r"(EGP|ج\.م|جنيه(\s*مصري)?|ريال)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^0-9\.,\s]", " ", t)
    t = normalize_spaces(t)
    cands = re.findall(r"\d[\d\s\.,]*", t)
    for c in cands:
        c2 = c.replace(" ", "").replace(",", "")
        if c2.count(".") == 1 and len(c2.split(".")[-1]) == 3 and len(c2.replace(".", "")) >= 5:
            c2 = c2.replace(".", "")
        try:
            val = float(c2)
        except:
            continue
        if 800 <= val <= 1_000_000:
            return val
    return None


def looks_like_phone(title: str) -> bool:
    t = (title or "").lower()
    if any(k in t for k in NOT_PHONE_SERIES):
        return False
    if any(k in t for k in ACCESSORY_KILL):
        return False
    return any(k in t for k in SMARTPHONE_HINTS)


def pick_brand_series_model(t: str) -> Tuple[str, Optional[str], str]:
    tl = f" {t.lower()} "
    brand = None
    series = None

    for b in ["iphone","samsung","xiaomi","redmi","poco","oppo","reno","realme","huawei","honor","vivo","nokia","oneplus","motorola","infinix","tecno","sony","galaxy"]:
        if f" {b} " in tl:
            if b in SERIES_TO_BRAND:
                series = b
                brand = SERIES_TO_BRAND[b]
            else:
                brand = b
            break

    # iPhone: keep the generation number
    if " iphone " in tl:
        m = re.search(r"iphone\s+(\d{1,2}[eE]?)\s*(pro\s*max|pro|plus|ultra|air|mini)?", t, re.I)
        if m:
            num = m.group(1)
            suf = (m.group(2) or "").strip()
            model = f"{num} {suf}".strip()
            model = re.sub(r"\s+", " ", model).title()
            return ("apple", None, model)
        m2 = re.search(r"iphone\s+(air|mini)", t, re.I)
        if m2:
            return ("apple", None, m2.group(1).title())
        return ("apple", None, "")

    if " galaxy " in tl:
        m = re.search(r"galaxy\s+([a-z0-9]+(?:\s?[a-z0-9]+)*)", t, re.I)
        if m:
            return ("samsung", "galaxy", m.group(1).strip())

    for fam in ["redmi","poco","xiaomi"]:
        if f" {fam} " in tl:
            m = re.search(rf"{fam}\s+([a-z0-9\- ]+)", t, re.I)
            if m:
                b = SERIES_TO_BRAND.get(fam, fam)
                ser = fam if fam in SERIES_TO_BRAND else None
                return (b, ser, m.group(1).strip())

    if brand:
        m = re.search(rf"{brand}\s+([a-z0-9\- ]+)", t, re.I)
        if m:
            return (brand, None, m.group(1).strip())

    return (brand or "", None, "")


def parse_suffix(t: str) -> str:
    tt = t.replace("جيجا بايت","GB").replace("جيجابايت","GB")
    caps = re.findall(r"(\d{2,4}\s?GB|\d{1,2}\s?TB)", tt, re.I)
    ram  = re.findall(r"(\d{1,2})\s?GB\s?RAM", tt, re.I) or re.findall(r"RAM\s?(\d{1,2})\s?GB", tt, re.I)
    flags = []
    if re.search(r"\b5G\b", tt, re.I):
        flags.append("5G")
    if re.search(r"Dual[\s-]?SIM|Dual\s?\/\s?Sim|Dual Sim|ثنائي الشريحة", tt, re.I):
        flags.append("Dual SIM")
    parts = []
    if ram:
        parts.append(f"{max(int(x) for x in ram)}GB RAM")
    if caps:
        def cap_to_num(x):
            x = x.lower().replace(" ", "")
            return (int(x[:-2]) * 1024) if x.endswith("tb") else int(x[:-2])
        parts.append(sorted(caps, key=cap_to_num, reverse=True)[0].upper().replace(" ", ""))
    parts.extend(flags)
    return " / ".join(parts)

# ------------- Page parsing -------------

def find_product_cards(soup: BeautifulSoup):
    for sel in [
        ".products.list .product-item",
        ".products.grid .product-item",
        ".product-items .product-item",
        ".product-item",
        "li.item.product",
        "div.item.product",
    ]:
        cards = soup.select(sel)
        if cards:
            return cards
    return []

PREORDER_PAT = re.compile(r"pre[- ]?order|pre\s?order|طلب\s?مسبق", re.I)


def extract_card(card, lang: str, origin: str) -> Optional[Dict]:
    title, link = None, None
    for sel in [".product-item-name a", ".product-item-link", "a.product-item-link", "a[title]"]:
        el = card.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            link = el.get("href")
            break
    if not title:
        el = card.select_one(".product-item-name") or card.find(["h2","h3","h4"]) 
        if el:
            title = el.get_text(strip=True)
    if not title:
        return None

    title = normalize_spaces(title)
    if not looks_like_phone(title):
        return None

    if not link:
        a = card.find("a", href=True)
        link = a["href"] if a else None
    if link and link.startswith("/"):
        base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
        link = urljoin(base, link)
    if not link:
        return None

    price_text = ""
    for sel in [".price", ".special-price .price", ".price-wrapper", ".price-box", "[data-price-type='finalPrice']"]:
        el = card.select_one(sel)
        if el and el.get_text(strip=True):
            price_text = el.get_text(" ", strip=True)
            break
    price = parse_price(price_text)

    norm = normalize_for_parse(title)
    brand, series, model = pick_brand_series_model(norm)
    suffix = parse_suffix(norm)

    return {
        "store": STORE, "country": COUNTRY, "currency": CURRENCY,
        "title": title, "link": link, "price": price,
        "category": "mobiles",  # repo-wide label
        "brand": brand, "series": series, "model": model, "suffix": suffix,
        "origin": origin, "scraped_at": now_iso(), "lang": lang,
    }

# ------------- Crawlers (requests) -------------

def paginate_category(session: requests.Session, url: str, max_pages: int, lang: str) -> List[Dict]:
    out: List[Dict] = []
    page = 1
    while page <= max_pages and url:
        soup = get_soup(session, url, lang)
        if soup is None:
            print(f"[2B][cat {lang}] page {page}: FETCH FAILED (403/429/503/404)")
            break
        cards = find_product_cards(soup)
        kept = 0
        for c in cards:
            item = extract_card(c, lang=lang, origin="category")
            if item:
                item["__query"] = "category"
                out.append(item)
                kept += 1
        # next page
        next_link = None
        for sel in ["a.action.next", "li.pages-item-next a", "a[rel='next']", "a.page-next"]:
            a = soup.select_one(sel)
            if a and a.get("href"):
                next_link = a.get("href")
                break
        print(f"[2B][cat {lang}] page {page}: cards={len(cards)} kept={kept}")
        if not next_link:
            break
        # absolute-ify next link if needed
        if next_link.startswith("/"):
            base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
            next_link = urljoin(base, next_link)
        url = next_link
        page += 1
    return out


def search_pages(session: requests.Session, term: str, max_pages: int, lang: str) -> List[Dict]:
    base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
    out: List[Dict] = []
    for p in range(1, max_pages + 1):
        url = urljoin(base, "catalogsearch/result/?" + urlencode({"q": term, "p": p}))
        soup = get_soup(session, url, lang)
        if soup is None:
            print(f"[2B][search {lang}] '{term}' p{p}: FETCH FAILED (403/429/503/404)")
            break
        cards = find_product_cards(soup)
        kept = 0
        for c in cards:
            item = extract_card(c, lang=lang, origin="search")
            if item:
                item["__query"] = term
                out.append(item)
                kept += 1
        print(f"[2B][search {lang}] '{term}' p{p}: cards={len(cards)} kept={kept}")
        if len(cards) == 0 or (kept == 0 and p >= 2):
            break
    return out

# ------------- Dedupe & Output -------------

def dedupe(items: List[Dict]) -> List[Dict]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict] = []
    for x in items:
        key = (x["link"], x.get("suffix") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def save_outputs(rows: List[Dict], csv_path: str, json_path: str):
    fields = [
        "store","country","currency","title","link","price",
        "category","brand","series","model","suffix","origin","scraped_at","lang","__query"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Wrote CSV: {csv_path}\nWrote JSON: {json_path}")

# -------- Supabase mapping (matches your table) --------

def to_supabase_record(item: Dict) -> Dict:
    # brand_or_model compact string
    brand_or_model = ""
    if item.get("brand"):
        bm = [item["brand"].title()]
        if item.get("series"):
            bm.append(item["series"].title())
        brand_or_model = " ".join(bm)
    elif item.get("model"):
        brand_or_model = item["model"]

    return {
        "store": STORE,
        "title": item.get("title", ""),
        "price": item.get("price"),
        "category": "mobiles",
        "query": item.get("__query", ""),
        "brand_or_model": brand_or_model,
        "model": item.get("model") or "",
        "suffix": item.get("suffix") or "",
        "link": item.get("link") or "",
        "country": COUNTRY,
        "currency": CURRENCY,
        "raw_title": item.get("title", ""),
    }


def supabase_upsert_all(rows: List[Dict]):
    url = os.getenv("SUPABASE_URL", "").strip().strip('"').strip("'")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    table = os.getenv("SUPABASE_TABLE", "products")
    if not (url and key and create_client):
        print("Supabase not configured; skipping upsert.")
        return
    try:
        supa = create_client(url, key)
        payload = [to_supabase_record(r) for r in rows]
        chunk = 500
        for i in range(0, len(payload), chunk):
            supa.table(table).upsert(payload[i:i+chunk]).execute()
        print(f"Upserted {len(payload)} rows into {table}.")
    except Exception as e:
        print("Supabase upsert failed:", e)

# ------------- Main -------------

def main():
    ap = argparse.ArgumentParser(description="Scrape 2B smartphones (resilient, requests-only).", add_help=True)
    ap.add_argument("--lang", choices=["en","ar"], default=DEFAULT_LANG)
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    ap.add_argument("--csv", type=str, default=DEFAULT_OUT_CSV)
    ap.add_argument("--json", type=str, default=DEFAULT_OUT_JSON)
    ap.add_argument("--no-search", action="store_true", help="Skip brand search fallback")
    ap.add_argument("--terms", type=str, default=",".join(DEFAULT_SEARCH_TERMS), help="Comma-separated search terms")
    args = ap.parse_args()

    session = build_session(args.lang)
    rows: List[Dict] = []

    # resolve category
    cat_url = resolve_category_url(session, args.lang)
    if cat_url:
        rows.extend(paginate_category(session, cat_url, max_pages=args.max_pages, lang=args.lang))
    else:
        print("[2B] Skipping category crawl (no working URL); continuing with search sweep...")

    # search sweep
    if not args.no_search:
        for term in [t.strip() for t in (args.terms or "").split(",") if t.strip()]:
            rows.extend(search_pages(session, term, max_pages=args.max_pages, lang=args.lang))

    print(f"Collected {len(rows)} raw rows before dedupe.")

    rows = dedupe(rows)
    print(f"Kept {len(rows)} rows after dedupe.")

    # local files (optional, useful for debugging)
    save_outputs(rows, csv_path=args.csv, json_path=args.json)

    # Supabase upsert (always attempted if env is present)
    if rows:
        supabase_upsert_all(rows)

if __name__ == "__main__":
    main()
