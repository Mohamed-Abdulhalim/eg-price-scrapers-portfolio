#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2B smartphones scraper — repo-ready edition

This version aligns with your Supabase schema and GitHub Action style.
- Zero-arg default: crawls 2B Smartphones category + brand search sweep
- Strict accessory filtering; English-normalized parsing; iPhone model keeps number
- Dedupe by (link, suffix)
- Exports CSV/JSON locally (optional) AND upserts to Supabase `products`
- Only sends columns that exist in your table: 
  store, title, price, category, query, brand_or_model, model, suffix, link, country, currency, raw_title

Env:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (preferred) or SUPABASE_ANON_KEY (fallback)
  SUPABASE_TABLE=products (optional)

Category label unified to: "mobiles"
Query field values:
  - "category" for category crawl results
  - the actual search term for search results (e.g., "iphone")
"""
import os, re, time, csv, json, random, argparse
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urljoin, urlencode

# ---------------- Defaults ----------------
DEFAULT_LANG = "en"               # crawl site root: en or ar
DEFAULT_MAX_PAGES = 10            # pagination depth for category and search
DEFAULT_OUT_CSV = "2b_smartphones.csv"
DEFAULT_OUT_JSON = "2b_smartphones.json"
DEFAULT_HEADLESS = True
DEFAULT_SEARCH_TERMS = [
    "iphone","apple","samsung","galaxy","xiaomi","redmi","poco","oppo","reno","realme",
    "huawei","honor","vivo","nokia","oneplus","motorola","infinix","tecno","sony",
    # Arabic safety nets
    "ايفون","ابل","سامسونج","شاومي","ريدمي","بوكو","اوبو","ريلمي","هواوي","هونر","فيفو","نوكيا","انفنيكس","تكنو","سوني",
]

CATEGORY_EN = "https://2b.com.eg/en/mobile-tablets/mobile-phones.html"
CATEGORY_AR = "https://2b.com.eg/ar/mobile-tablets/mobile-phones.html"

STORE = VENDOR = "2B"
COUNTRY = "EG"
CURRENCY = "EGP"

# ---------------- Selenium ----------------
USE_UC = True
try:
    import undetected_chromedriver as uc
except Exception:
    USE_UC = False

from bs4 import BeautifulSoup

# Supabase client
try:
    from supabase import create_client
except Exception:
    create_client = None

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
IPHONE_MODELS = ["Pro Max","Pro","Plus","Ultra","Air","Mini"]

# ---------------- Utils ----------------

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
    """Return (brand, series, model) in EN; model keeps iPhone generation."""
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

    # iPhone: keep the number
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
    if re.search(r"Dual[\s-]?SIM|Dual\s?\/?\s?Sim|Dual Sim|ثنائي الشريحة", tt, re.I):
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

# ------------- Selenium helpers -------------

def make_driver(headless=DEFAULT_HEADLESS):
    if USE_UC:
        opts = uc.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1360,2200")
        return uc.Chrome(options=opts, use_subprocess=True)
    else:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1360,2200")
        return webdriver.Chrome(options=opts)


def get_soup(driver, url: str) -> BeautifulSoup:
    driver.get(url)
    time.sleep(1.1 + random.random())
    return BeautifulSoup(driver.page_source, "html.parser")


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
        if cards: return cards
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
        if el: title = el.get_text(strip=True)
    if not title: return None

    title = normalize_spaces(title)
    if not looks_like_phone(title):
        return None

    if not link:
        a = card.find("a", href=True)
        link = a["href"] if a else None
    if link and link.startswith("/"):
        base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
        link = urljoin(base, link)
    if not link: return None

    price_text = ""
    for sel in [".price", ".special-price .price", ".price-wrapper", ".price-box", "[data-price-type='finalPrice']"]:
        el = card.select_one(sel)
        if el and el.get_text(strip=True):
            price_text = el.get_text(" ", strip=True); break
    price = parse_price(price_text)

    # parse
    norm = normalize_for_parse(title)
    brand, series, model = pick_brand_series_model(norm)
    suffix = parse_suffix(norm)

    return {
        "store": STORE, "vendor": VENDOR, "country": COUNTRY, "currency": CURRENCY,
        "title": title, "link": link, "price": price,
        "category": "mobiles",  # repo-wide label
        "brand": brand, "series": series, "model": model, "suffix": suffix,
        "origin": origin, "scraped_at": now_iso(), "lang": lang,
    }

# ------------- Crawlers -------------

def paginate_category(driver, url: str, max_pages: int, lang: str) -> List[Dict]:
    out: List[Dict] = []
    page = 1
    while page <= max_pages:
        soup = get_soup(driver, url)
        cards = find_product_cards(soup)
        kept = 0
        for c in cards:
            item = extract_card(c, lang=lang, origin="category")
            if item:
                item["__query"] = "category"
                out.append(item); kept += 1
        # next page
        next_link = None
        for sel in ["a.action.next", "li.pages-item-next a", "a[rel='next']", "a.page-next"]:
            a = soup.select_one(sel)
            if a and a.get("href"): next_link = a["href"]; break
        print(f"[2B][cat {lang}] page {page}: cards={len(cards)} kept={kept}")
        if not next_link: break
        url = next_link; page += 1
    return out


def search_pages(driver, term: str, max_pages: int, lang: str) -> List[Dict]:
    base = "https://2b.com.eg/ar/" if lang == "ar" else "https://2b.com.eg/en/"
    out: List[Dict] = []
    for p in range(1, max_pages + 1):
        url = urljoin(base, "catalogsearch/result/?" + urlencode({"q": term, "p": p}))
        soup = get_soup(driver, url)
        cards = find_product_cards(soup)
        kept = 0
        for c in cards:
            item = extract_card(c, lang=lang, origin="search")
            if item:
                item["__query"] = term
                out.append(item); kept += 1
        print(f"[2B][search {lang}] '{term}' p{p}: cards={len(cards)} kept={kept}")
        if len(cards) == 0 or (kept == 0 and p >= 2):
            break
    return out

# ------------- Dedupe & Output -------------

def dedupe(items: List[Dict]) -> List[Dict]:
    seen: Set[Tuple[str, str]] = set(); out: List[Dict] = []
    for x in items:
        key = (x["link"], x.get("suffix") or "")
        if key in seen: continue
        seen.add(key); out.append(x)
    return out


def save_outputs(rows: List[Dict], csv_path: str, json_path: str):
    fields = [
        "store","vendor","country","currency","title","link","price",
        "category","brand","series","model","suffix","origin","scraped_at","lang","__query"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in fields})
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
        # created_at left to DB default
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
    ap = argparse.ArgumentParser(description="Scrape 2B smartphones. Zero-arg default.", add_help=True)
    ap.add_argument("--lang", choices=["en","ar"], default=DEFAULT_LANG)
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    ap.add_argument("--csv", type=str, default=DEFAULT_OUT_CSV)
    ap.add_argument("--json", type=str, default=DEFAULT_OUT_JSON)
    ap.add_argument("--headless", action="store_true", default=DEFAULT_HEADLESS)
    ap.add_argument("--no-search", action="store_true", help="Skip brand search fallback")
    ap.add_argument("--terms", type=str, default=",".join(DEFAULT_SEARCH_TERMS), help="Comma-separated search terms")
    args = ap.parse_args()

    # driver
    driver = make_driver(headless=args.headless)
    rows: List[Dict] = []
    try:
        cat_url = CATEGORY_AR if args.lang == "ar" else CATEGORY_EN
        rows.extend(paginate_category(driver, cat_url, max_pages=args.max_pages, lang=args.lang))
        if not args.no_search:
            for term in [t.strip() for t in (args.terms or "").split(",") if t.strip()]:
                rows.extend(search_pages(driver, term, max_pages=args.max_pages, lang=args.lang))
        print(f"Collected {len(rows)} raw rows before dedupe.")
    finally:
        try: driver.quit()
        except Exception: pass

    rows = dedupe(rows)
    print(f"Kept {len(rows)} rows after dedupe.")

    # local files (optional, useful for debugging)
    save_outputs(rows, csv_path=args.csv, json_path=args.json)

    # Supabase upsert (always attempted if env is present)
    if rows:
        supabase_upsert_all(rows)

if __name__ == "__main__":
    main()
