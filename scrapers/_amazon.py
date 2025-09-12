# ✅ Updated Amazon Egypt Scraper with Debug Logs
# - Debug logs for why items are skipped
# - Better link extraction for valid /dp/ links
# - Shows extracted title, price, link if found

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from supabase import create_client, Client

# --- Supabase Setup ---
import os, sys

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # use service_role for writes
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY (set as Actions secrets and mapped in scrape.yml).")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]

CATEGORY_MAPPING = {
    'phones': '21832883031',
    'mobile': '21832883031',
    'mobiles': '21832883031'
}

ACCESSORY_KEYWORDS = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger", "cable", "headset",
    "جراب", "حافظة", "زجاج", "واقي", "شاحن", "كابل", "سماعة", "لاصقة", "كفر", "حماية", "غطاء",
    "شاشة", "سماعات", "قلم", "عدسة", "غطى", "كاميرا", "سلك", "بطارية", "حقيبة", "محفظة",
    "جلد", "سيليكون", "اسكرين", "باور بانك", "سكرين"
]

def normalize_arabic(text):
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"[ى]", "ي", text)
    text = re.sub(r"[ة]", "ه", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_accessory(title):
    title_norm = normalize_arabic(title).lower()
    for word in ACCESSORY_KEYWORDS:
        if word in title_norm:
            return True
    return False

def extract_brand_or_model(title):
    title_norm = normalize_arabic(title.lower())
    brand_map = {
        "ايفون": "ايفون", "آيفون": "ايفون", "apple": "Apple", "ابل": "Apple",
        "سامسونج": "سامسونج", "samsung": "Samsung",
        "ريلمي": "ريلمي", "realme": "Realme",
        "هواوي": "هواوي", "huawei": "Huawei",
        "شاومي": "شاومي", "xiaomi": "Xiaomi",
        "اوبو": "اوبو", "oppo": "Oppo",
        "فيفو": "فيفو", "vivo": "Vivo",
        "نوكيا": "نوكيا", "nokia": "Nokia",
        "سوني": "سوني", "sony": "Sony",
        "جوجل": "جوجل", "google": "Google Pixel",
        "موتورولا": "موتورولا", "motorola": "Motorola",
        "ون بلس": "ون بلس", "oneplus": "OnePlus",
        "ال جي": "ال جي", "lg": "LG",
        "بوكو": "بوكو", "poco": "Poco"
    }

    for keyword, brand in brand_map.items():
        if keyword in title_norm:
            return brand
    return "Unknown"

def extract_model_and_suffix(title):
    title = normalize_arabic(title)
    suffix = ""

    # سuffix = "Pro" or "برو"
    suffix_match = re.search(r"\b(pro|برو)\b", title, re.IGNORECASE)
    if suffix_match:
        suffix = suffix_match.group(1).capitalize()

    # Samsung model like "ايه 55" -> A55
    match = re.search(r"\bايه\s*(\d{1,3})\b", title)
    if match:
        return f"A{match.group(1)}", suffix

    # Redmi "نوت 13" → Note 13
    if "ريدمي" in title and "نوت" in title:
        note_match = re.search(r"نوت\s*(\d{1,3})", title)
        if note_match:
            return f"Note{note_match.group(1)}", "نوت" if not suffix else suffix

    # General models like "S23", "C53", "13 Pro"
    match = re.search(r"\b([a-zA-Z]{1,2}\d{1,3}[a-zA-Z+]{0,4})\b", title, re.IGNORECASE)
    if match:
        return match.group(1).upper(), suffix

    return None, suffix

def build_search_url(keyword, category_code=None, page=1):
    base_url = 'https://www.amazon.eg/s'
    params = {'k': keyword, 'page': str(page)}
    if category_code and category_code.isdigit():
        params['rh'] = f'n:{category_code}'
    return requests.Request('GET', base_url, params=params).prepare().url

def get_products_from_search(keyword, category_code=None):
    products = []
    seen_links = set()

    for page in range(1, 4):
        url = build_search_url(keyword, category_code, page)
        print(f"[+] Accessing: {url}")

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "ar-EG,ar;q=0.9",
            "Referer": "https://www.amazon.eg/",
        }

        session = requests.Session()
        response = session.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            print("[!] Failed to fetch page")
            continue

        soup = BeautifulSoup(response.content, 'html.parser')
        results = soup.find_all('div', {'data-component-type': 's-search-result'})
        print(f"[+] Found {len(results)} raw results on page {page}")

        for item in results:
            title_tag = item.find('h2')
            title = title_tag.get_text(strip=True) if title_tag else None

            price_whole = item.find('span', {'class': 'a-price-whole'})
            price_fraction = item.find('span', {'class': 'a-price-fraction'})

            if price_whole:
                try:
                    whole_digits = re.sub(r'[^\d]', '', price_whole.text)
                    fraction_digits = price_fraction.text if price_fraction else '00'
                    price = float(f"{whole_digits}.{fraction_digits}")
                except:
                    price = None
            else:
                price = None

            a_tag = item.find('a', href=True)
            link = 'https://www.amazon.eg' + a_tag['href'].split('?')[0] if a_tag and '/dp/' in a_tag['href'] else None

            if not title or not price or not link:
                continue
            if is_accessory(title) or price < 1000 or link in seen_links:
                continue

            seen_links.add(link)
            brand_or_model = extract_brand_or_model(title)
            model, suffix = extract_model_and_suffix(title)

            product = {
                'title': title,
                'price': price,
                'store': 'Amazon',
                'category': 'mobiles',
                'query': keyword,
                'brand_or_model': brand_or_model,
                'model': model,
                'suffix': suffix
            }

            # Upload to Supabase
            try:
                supabase.table("products").insert(product).execute()
                print(f"✅ Uploaded: {title[:40]}... - {price} EGP")
            except Exception as e:
                print(f"[!] Supabase insert failed: {e}")

            products.append(product)

        time.sleep(random.uniform(3, 6))

    return products

if __name__ == "__main__":
    keywords = [
        "iphone", "samsung", "xiaomi", "oppo", "huawei",
        "realme", "vivo", "oneplus", "poco", "nokia", "sony", "lg"
    ]
    category_code = CATEGORY_MAPPING.get("mobiles")

    all_products = []
    for kw in keywords:
        print(f"\n=== Searching for: {kw} ===")
        prods = get_products_from_search(kw, category_code)
        all_products.extend(prods)

    print(f"\n✅ Total products uploaded: {len(all_products)}")


























# import requests
# from bs4 import BeautifulSoup
# import re
# import time
# import csv
# import random

# USER_AGENTS = [
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
# ]

# CATEGORY_MAPPING = {
#     'phones': '21832883031',
#     'mobile': '21832883031',
#     'mobiles': '21832883031'
# }

# ACCESSORY_KEYWORDS = [
#     "case", "cover", "screen", "protector", "glass", "accessory", "charger", "cable", "headset",
#     "جراب", "حافظة", "زجاج", "واقي", "شاحن", "كابل", "سماعة", "لاصقة", "كفر", "حماية", "غطاء",
#     "شاشة", "سماعات", "قلم", "عدسة", "غطى", "كاميرا", "سلك", "بطارية", "حقيبة", "محفظة",
#     "جلد", "سيليكون", "اسكرين", "باور بانك", "سكرين"
# ]

# BRANDS = [
#     "iphone", "apple",
#     "samsung", "galaxy",
#     "huawei",
#     "xiaomi",
#     "oppo",
#     "vivo",
#     "oneplus",
#     "realme",
#     "google pixel",
#     "nokia",
#     "sony",
#     "lg",
#     "motorola",
#     "بوكو",
#     "ريدمي"
# ]

# def normalize_arabic(text):
#     text = re.sub(r"[إأآا]", "ا", text)
#     text = re.sub(r"[ى]", "ي", text)
#     text = re.sub(r"[ة]", "ه", text)
#     text = re.sub(r"\s+", " ", text)
#     return text.strip()

# def is_accessory(title):
#     title_norm = normalize_arabic(title).lower()
#     title_lower = title.lower()
#     for word in ACCESSORY_KEYWORDS:
#         if word in title_norm or word in title_lower:
#             return True
#     return False

# def extract_brand_or_model(title):
#     title_norm = normalize_arabic(title.lower())

#     brand_keywords = {
#         "ايفون": "ايفون", "آيفون": "ايفون", "apple": "Apple", "ابل": "Apple",
#         "سامسونج": "سامسونج", "samsung": "Samsung",
#         "ريلمي": "ريلمي", "realme": "Realme",
#         "هواوي": "هواوي", "huawei": "Huawei",
#         "شاومي": "شاومي", "xiaomi": "Xiaomi",
#         "اوبو": "اوبو", "oppo": "Oppo",
#         "فيفو": "فيفو", "vivo": "Vivo",
#         "نوكيا": "نوكيا", "nokia": "Nokia",
#         "سوني": "سوني", "sony": "Sony",
#         "جوجل": "جوجل", "google": "Google Pixel",
#         "موتورولا": "موتورولا", "motorola": "Motorola",
#         "ون بلس": "ون بلس", "oneplus": "OnePlus",
#         "ال جي": "ال جي", "lg": "LG",
#         "بوكو": "بوكو",
#         "ريدمي": "ريدمي"
#     }

#     for keyword, brand in brand_keywords.items():
#         if keyword in title_norm:
#             return brand

#     return "Unknown"

# def extract_model_and_suffix(title):
#     title = normalize_arabic(title)
#     suffix = ""

#     suffix_match = re.search(r"\b(pro|برو)\b", title, re.IGNORECASE)
#     if suffix_match:
#         suffix = suffix_match.group(1).capitalize()

#     if "ريدمي" in title and "نوت" in title:
#         suffix = "نوت"

#     samsung_arabic_model = re.search(r"\bايه\s*(\d{1,3})\b", title)
#     if samsung_arabic_model:
#         return f"A{samsung_arabic_model.group(1)}", suffix

#     general_model = re.search(r"\b(?:ايفون|iphone|samsung|galaxy|بوكو|ريدمي|note|نوت)?\s*([a-zA-Z]?[0-9]{1,4}[a-zA-Z+]?)\b", title, re.IGNORECASE)
#     if general_model:
#         return general_model.group(1).upper(), suffix

#     return None, suffix

# def build_search_url(keyword, category_code=None, page=1):
#     base_url = 'https://www.amazon.eg/s'
#     params = {'k': keyword, 'page': str(page)}
#     if category_code and category_code.isdigit():
#         params['rh'] = f'n:{category_code}'
#     return requests.Request('GET', base_url, params=params).prepare().url

# def extract_title(item):
#     title_tag = item.find('h2')
#     if title_tag:
#         return title_tag.get_text(strip=True)
#     return None

# def extract_price(item):
#     whole = item.find('span', {'class': 'a-price-whole'})
#     fraction = item.find('span', {'class': 'a-price-fraction'})
#     if whole:
#         try:
#             whole_digits = re.sub(r'[^\d]', '', whole.text)
#             fraction_digits = fraction.text if fraction else '00'
#             price = float(f"{whole_digits}.{fraction_digits}")
#             return price
#         except:
#             return None
#     return None

# def extract_link(item):
#     a_tag = item.find('a', href=True)
#     if a_tag and '/dp/' in a_tag['href']:
#         return 'https://www.amazon.eg' + a_tag['href'].split('?')[0]
#     return None

# def get_products_from_search(keyword, category_code=None):
#     products = []
#     seen_links = set()

#     for page in range(1, 4):
#         url = build_search_url(keyword, category_code, page)
#         print(f"[+] Accessing: {url}")

#         headers = {
#             "User-Agent": USER_AGENTS[0],
#             "Accept-Language": "ar-EG,ar;q=0.9",
#             "Referer": "https://www.amazon.eg/",
#             "DNT": "1",
#             "Upgrade-Insecure-Requests": "1",
#             "Sec-Fetch-Dest": "document",
#             "Sec-Fetch-Mode": "navigate",
#             "Sec-Fetch-Site": "same-origin",
#             "Sec-Fetch-User": "?1",
#         }

#         session = requests.Session()
#         response = session.get(url, headers=headers, timeout=20)
#         if response.status_code != 200:
#             print("[!] Failed to fetch page")
#             continue

#         soup = BeautifulSoup(response.content, 'html.parser')
#         results = soup.find_all('div', {'data-component-type': 's-search-result'})

#         print(f"[+] Found {len(results)} raw results on page {page}")

#         for item in results:
#             title = extract_title(item)
#             price = extract_price(item)
#             link = extract_link(item)

#             if not title or not price or not link:
#                 continue
#             if is_accessory(title):
#                 continue
#             if link in seen_links:
#                 continue
#             if price < 1000:
#                 continue

#             seen_links.add(link)

#             brand_or_model = extract_brand_or_model(title) or "Unknown"
#             model, suffix = extract_model_and_suffix(title)

#             products.append({
#                 'title': title,
#                 'price': price,
#                 'link': link,
#                 'store': 'Amazon',
#                 'category': 'mobiles',
#                 'query': keyword,
#                 'brand_or_model': brand_or_model,
#                 'model': model,
#                 'suffix': suffix
#             })

#         if not results:
#             break

#         time.sleep(random.uniform(3, 6))

#     return products

# def save_products_to_csv(products, filename='products.csv'):
#     fieldnames = ['title', 'price', 'link', 'store', 'category', 'query', 'brand_or_model', 'model', 'suffix']
#     with open(filename, mode='w', newline='', encoding='utf-8-sig') as f:
#         writer = csv.DictWriter(f, fieldnames=fieldnames)
#         writer.writeheader()
#         for product in products:
#             writer.writerow(product)
#     print(f"✅ Saved {len(products)} products to '{filename}'")

# if __name__ == '__main__':
#     keywords = BRANDS
#     category_input = "mobiles"
#     category_code = CATEGORY_MAPPING.get(category_input)

#     all_products = []
#     for kw in keywords:
#         print(f"\n=== Searching for: {kw} ===")
#         prods = get_products_from_search(kw, category_code)
#         all_products.extend(prods)

#     print(f"\nTotal products found: {len(all_products)}")
#     save_products_to_csv(all_products)


































# import requests
# from bs4 import BeautifulSoup
# import re
# import time
# import csv
# import random

# USER_AGENTS = [
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
# ]

# CATEGORY_MAPPING = {
#     'phones': '21832883031',
#     'mobile': '21832883031',
#     'mobiles': '21832883031'
# }

# ACCESSORY_KEYWORDS = [
#     "case", "cover", "screen", "protector", "glass", "accessory", "charger", "cable", "headset",
#     "جراب", "حافظة", "زجاج", "واقي", "شاحن", "كابل", "سماعة", "لاصقة", "كفر", "حماية", "غطاء",
#     "شاشة", "سماعات", "قلم", "عدسة", "غطى", "كاميرا", "سلك", "بطارية", "حقيبة", "محفظة",
#     "جلد", "سيليكون", "اسكرين", "باور بانك", "سكرين"
# ]

# BRANDS = [
#     "iphone", "apple",
#     "samsung", "galaxy",
#     "huawei",
#     "xiaomi",
#     "oppo",
#     "vivo",
#     "oneplus",
#     "realme",
#     "google pixel",
#     "nokia",
#     "sony",
#     "lg",
#     "motorola",
# ]

# def normalize_arabic(text):
#     text = re.sub(r"[إأآا]", "ا", text)  # Normalize Arabic letters
#     text = re.sub(r"[ى]", "ي", text)
#     text = re.sub(r"[ة]", "ه", text)
#     text = re.sub(r"\s+", " ", text)
#     return text.strip()

# def is_accessory(title):
#     title_norm = normalize_arabic(title).lower()
#     title_lower = title.lower()
#     for word in ACCESSORY_KEYWORDS:
#         if word in title_norm or word in title_lower:
#             return True
#     return False

# def extract_brand_or_model(title):
#     title_lower = title.lower()

#     # Normalize common brand names in Arabic
#     arabic_brand_map = {
#         "ايفون": "ايفون", "آيفون": "ايفون", "apple": "Apple", "ابل": "Apple",
#         "سامسونج": "سامسونج", "samsung": "Samsung",
#         "ريلمي": "ريلمي", "realme": "Realme",
#         "هواوي": "هواوي", "huawei": "Huawei",
#         "شاومي": "شاومي", "xiaomi": "Xiaomi",
#         "اوبو": "اوبو", "oppo": "Oppo",
#         "فيفو": "فيفو", "vivo": "Vivo",
#         "نوكيا": "نوكيا", "nokia": "Nokia",
#         "سوني": "سوني", "sony": "Sony",
#         "جوجل": "جوجل", "google": "Google Pixel",
#         "موتورولا": "موتورولا", "motorola": "Motorola",
#         "ون بلس": "ون بلس", "oneplus": "OnePlus",
#         "ال جي": "ال جي", "lg": "LG",
#     }

#     title_norm = normalize_arabic(title.lower())

#     for keyword, brand in arabic_brand_map.items():
#         if keyword in title_norm:
#             return brand

#     return None  # Don't fall back to generic first word

# def extract_model_and_suffix(title):
#     title = normalize_arabic(title)
#     suffix = ""

#     # Only assign suffix if it's 'pro' or 'برو'
#     suffix_match = re.search(r"\b(pro|برو)\b", title, re.IGNORECASE)
#     if suffix_match:
#         suffix = suffix_match.group(1).capitalize()

#     # Samsung Arabic model like ايه 55 → A55
#     samsung_arabic_model = re.search(r"\bايه\s*(\d{1,3})\b", title)
#     if samsung_arabic_model:
#         return f"A{samsung_arabic_model.group(1)}", suffix

#     # General models (iPhone, Samsung, etc.)
#     general_model = re.search(r"\b(?:ايفون|iphone|samsung|galaxy)?\s*([a-zA-Z]?[0-9]{1,4}[a-zA-Z+]?)\b", title, re.IGNORECASE)
#     if general_model:
#         return general_model.group(1).upper(), suffix

#     return None, suffix

# def build_search_url(keyword, category_code=None, page=1):
#     base_url = 'https://www.amazon.eg/s'
#     params = {'k': keyword, 'page': str(page)}
#     if category_code and category_code.isdigit():
#         params['rh'] = f'n:{category_code}'
#     return requests.Request('GET', base_url, params=params).prepare().url

# def extract_title(item):
#     title_tag = item.find('h2')
#     if title_tag:
#         return title_tag.get_text(strip=True)
#     return None

# def extract_price(item):
#     whole = item.find('span', {'class': 'a-price-whole'})
#     fraction = item.find('span', {'class': 'a-price-fraction'})
#     if whole:
#         try:
#             whole_digits = re.sub(r'[^\d]', '', whole.text)
#             fraction_digits = fraction.text if fraction else '00'
#             price = float(f"{whole_digits}.{fraction_digits}")
#             return price
#         except:
#             return None
#     return None

# def extract_link(item):
#     a_tag = item.find('a', href=True)
#     if a_tag and '/dp/' in a_tag['href']:
#         return 'https://www.amazon.eg' + a_tag['href'].split('?')[0]
#     return None

# def get_products_from_search(keyword, category_code=None):
#     products = []
#     seen_links = set()

#     for page in range(1, 4):
#         url = build_search_url(keyword, category_code, page)
#         print(f"[+] Accessing: {url}")

#         headers = {
#             "User-Agent": USER_AGENTS[0],
#             "Accept-Language": "ar-EG,ar;q=0.9",
#             "Referer": "https://www.amazon.eg/",
#             "DNT": "1",
#             "Upgrade-Insecure-Requests": "1",
#             "Sec-Fetch-Dest": "document",
#             "Sec-Fetch-Mode": "navigate",
#             "Sec-Fetch-Site": "same-origin",
#             "Sec-Fetch-User": "?1",
#         }

#         session = requests.Session()
#         response = session.get(url, headers=headers, timeout=20)
#         if response.status_code != 200:
#             print("[!] Failed to fetch page")
#             continue

#         soup = BeautifulSoup(response.content, 'html.parser')
#         results = soup.find_all('div', {'data-component-type': 's-search-result'})

#         print(f"[+] Found {len(results)} raw results on page {page}")

#         for item in results:
#             title = extract_title(item)
#             price = extract_price(item)
#             link = extract_link(item)

#             if not title or not price or not link:
#                 continue
#             if is_accessory(title):
#                 continue
#             if link in seen_links:
#                 continue
#             if price < 1000:
#                 continue

#             seen_links.add(link)

#             brand_or_model = extract_brand_or_model(title) or "Unknown"
#             model, suffix = extract_model_and_suffix(title)

#             products.append({
#                 'title': title,
#                 'price': price,
#                 'link': link,
#                 'store': 'Amazon',
#                 'category': 'mobiles',
#                 'query': keyword,
#                 'brand_or_model': brand_or_model,
#                 'model': model,
#                 'suffix': suffix
#             })

#         if not results:
#             break

#         time.sleep(random.uniform(3, 6))

#     return products

# def save_products_to_csv(products, filename='products.csv'):
#     fieldnames = ['title', 'price', 'link', 'store', 'category', 'query', 'brand_or_model', 'model', 'suffix']
#     with open(filename, mode='w', newline='', encoding='utf-8-sig') as f:
#         writer = csv.DictWriter(f, fieldnames=fieldnames)
#         writer.writeheader()
#         for product in products:
#             writer.writerow(product)
#     print(f"✅ Saved {len(products)} products to '{filename}'")

# if __name__ == '__main__':
#     keywords = BRANDS
#     category_input = "mobiles"
#     category_code = CATEGORY_MAPPING.get(category_input)

#     all_products = []
#     for kw in keywords:
#         print(f"\n=== Searching for: {kw} ===")
#         prods = get_products_from_search(kw, category_code)
#         all_products.extend(prods)

#     print(f"\nTotal products found: {len(all_products)}")
#     save_products_to_csv(all_products)







































# import requests
# from bs4 import BeautifulSoup
# import re
# import time
# import random
# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options
# import chromedriver_autoinstaller
# # from supabase import create_client, Client  # COMMENTED OUT, not needed for now

# # Auto-install chromedriver for fallback
# try:
#     chromedriver_autoinstaller.install()
# except:
#     pass

# # --- Supabase Setup ---
# # SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
# # SUPABASE_KEY = "your-supabase-key"  # COMMENTED OUT, not needed for now
# # supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)  # COMMENTED OUT, not needed for now

# USE_PROXY = False
# PROXIES = [
#     # Example proxies
# ]

# USER_AGENTS = [
#     "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
#     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
#     "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
#     "Mozilla/5.0 (iPad; CPU OS 13_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Mobile/15E148 Safari/604.1"
# ]

# CATEGORY_MAPPING = {
#     'phones': '21832883031',
#     'mobile': '21832883031',
#     'mobiles': '21832883031',
#     'smartphone': '21832883031',
#     'smartphones': '21832883031',
#     'electronics': 'electronics',
#     'computers': 'computers',
#     'laptops': 'laptops',
#     'tablets': 'tablets',
#     'headphones': 'headphones',
#     'watches': 'watches',
#     'cameras': 'cameras'
# }

# ACCESSORY_KEYWORDS = [
#     "case", "cover", "screen", "protector", "glass", "accessory", "charger", "cable", "headset",
#     "جراب", "حافظة", "زجاج", "واقي", "شاحن", "كابل", "سماعة", "لاصقة", "كفر", "حماية", "غطاء", 
#     "شاشة", "سماعات", "قلم", "عدسة", "غطى", "كاميرا", "سلك", "بطارية", "حقيبة", "محفظة", 
#     "جلد", "سيليكون", "اسكرين", "باور بانك", "سكرين"
# ]

# def normalize_arabic(text):
#     text = re.sub(r"[إأآا]", "ا", text)
#     text = re.sub(r"[ى]", "ي", text)
#     text = re.sub(r"[ة]", "ه", text)
#     text = re.sub(r"\s+", " ", text)
#     return text.strip()

# def is_accessory(title):
#     title_norm = normalize_arabic(title).lower()
#     title_lower = title.lower()

#     normalized_keywords = [normalize_arabic(word).lower() for word in ACCESSORY_KEYWORDS]

#     for word in normalized_keywords:
#         if word in title_norm or word in title_lower:
#             return True

#     return False

# def build_search_url(keyword, category_code=None):
#     base_url = 'https://www.amazon.eg/s'
#     params = {'k': keyword}
#     if category_code and category_code.isdigit():
#         params['rh'] = f'n:{category_code}'
#     return requests.Request('GET', base_url, params=params).prepare().url

# def try_selenium_scrape(url, max_retries=2):
#     """Fallback method using Selenium if requests fail"""
#     for attempt in range(max_retries):
#         try:
#             options = Options()
#             options.add_argument("--headless")
#             options.add_argument("--disable-gpu")
#             options.add_argument("--window-size=1920x1080")
#             options.add_argument("--disable-blink-features=AutomationControlled")
#             options.add_argument("--no-sandbox")
#             options.add_argument("--disable-dev-shm-usage")
#             options.add_experimental_option("excludeSwitches", ["enable-automation"])
#             options.add_experimental_option('useAutomationExtension', False)
            
#             driver = webdriver.Chrome(options=options)
#             driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
#             print(f"[🔄] Trying Selenium method (attempt {attempt + 1})...")
#             driver.get(url)
#             time.sleep(3)
            
#             page_source = driver.page_source
#             driver.quit()
            
#             return page_source
            
#         except Exception as e:
#             print(f"[!] Selenium attempt {attempt + 1} failed: {e}")
#             if 'driver' in locals():
#                 try:
#                     driver.quit()
#                 except:
#                     pass
            
#             if attempt < max_retries - 1:
#                 time.sleep(2)
    
#     return None

# def extract_title_from_item(item):
#     """Enhanced title extraction with multiple fallback methods"""
    
#     # Debug: Print the item structure to understand the HTML
#     print(f"[DEBUG] Item HTML structure: {str(item)[:200]}...")
    
#     # Method 1: Look for product title in h2 tag with span
#     h2_tag = item.find('h2', class_=re.compile(r'.*s-size.*'))
#     if h2_tag:
#         # Look for the main product link
#         link = h2_tag.find('a')
#         if link:
#             # Try to get text from the link
#             title_text = link.get_text(strip=True)
#             if len(title_text) > 10:
#                 print(f"[DEBUG] Method 1 found title: {title_text[:50]}...")
#                 return title_text
    
#     # Method 2: Look for any h2 with a link
#     h2_tags = item.find_all('h2')
#     for h2 in h2_tags:
#         link = h2.find('a')
#         if link:
#             title_text = link.get_text(strip=True)
#             if len(title_text) > 10:
#                 print(f"[DEBUG] Method 2 found title: {title_text[:50]}...")
#                 return title_text
    
#     # Method 3: Look for specific Amazon title selectors
#     title_selectors = [
#         'h2 a span',
#         '[data-cy="title-recipe-title"]',
#         'h2.a-size-mini span',
#         'h2 span',
#         '.s-title-instructions-style h2 a span'
#     ]
    
#     for selector in title_selectors:
#         elements = item.select(selector)
#         for element in elements:
#             title_text = element.get_text(strip=True)
#             if len(title_text) > 10:
#                 print(f"[DEBUG] Method 3 found title with selector {selector}: {title_text[:50]}...")
#                 return title_text
    
#     # Method 4: Broader search for any meaningful text
#     all_links = item.find_all('a')
#     for link in all_links:
#         if 'href' in link.attrs and '/dp/' in link.get('href', ''):
#             title_text = link.get_text(strip=True)
#             if len(title_text) > 15:  # Longer minimum for this method
#                 print(f"[DEBUG] Method 4 found title from product link: {title_text[:50]}...")
#                 return title_text
    
#     print("[DEBUG] No title found with any method")
#     return None

# def extract_price_from_item(item):
#     """Enhanced price extraction"""
    
#     # Method 1: Standard Amazon price structure
#     whole = item.find('span', {'class': 'a-price-whole'})
#     fraction = item.find('span', {'class': 'a-price-fraction'})
    
#     if whole:
#         whole_digits = re.sub(r'[^\d]', '', whole.text)
#         fraction_digits = fraction.text if fraction else '00'
#         full_price = f"{whole_digits}.{fraction_digits}"
        
#         try:
#             price = float(full_price)
#             print(f"[DEBUG] Method 1 found price: {price}")
#             return price
#         except ValueError:
#             pass
    
#     # Method 2: Look for any price-related spans
#     price_spans = item.find_all('span', class_=re.compile(r'.*price.*'))
#     for span in price_spans:
#         price_text = span.get_text(strip=True)
#         # Extract numbers from the price text
#         numbers = re.findall(r'[\d,]+\.?\d*', price_text)
#         for num_str in numbers:
#             try:
#                 # Remove commas and convert to float
#                 price = float(num_str.replace(',', ''))
#                 if price > 10:  # Reasonable minimum price
#                     print(f"[DEBUG] Method 2 found price: {price}")
#                     return price
#             except ValueError:
#                 continue
    
#     # Method 3: Look for currency symbols
#     currency_patterns = [
#         r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:EGP|جنيه|ج\.م)',
#         r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|\$)',
#     ]
    
#     item_text = item.get_text()
#     for pattern in currency_patterns:
#         matches = re.findall(pattern, item_text)
#         for match in matches:
#             try:
#                 price = float(match.replace(',', ''))
#                 if price > 10:
#                     print(f"[DEBUG] Method 3 found price: {price}")
#                     return price
#             except ValueError:
#                 continue
    
#     print("[DEBUG] No price found")
#     return None

# def get_products_from_search(keyword, category_code=None):
#     all_products = []
#     seen_titles = set()
    
#     for page in range(1, 4):  # Try up to 3 pages
#         url = build_search_url(keyword, category_code)
#         if page > 1:
#             url += f"&page={page}"
        
#         print(f"[+] Accessing page {page}: {url}")
        
#         headers = {
#             "User-Agent": random.choice(USER_AGENTS),
#             "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
#             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
#             "Accept-Encoding": "gzip, deflate, br",
#             "DNT": "1",
#             "Connection": "keep-alive",
#             "Upgrade-Insecure-Requests": "1",
#             "Referer": "https://www.amazon.eg/"
#         }

#         delay = random.uniform(2, 5)
#         print(f"[+] Sleeping for {round(delay, 2)} seconds to avoid detection...")
#         time.sleep(delay)

#         session = requests.Session()
#         session.headers.update(headers)

#         proxy = random.choice(PROXIES) if USE_PROXY and PROXIES else None
#         proxies = {"http": proxy, "https": proxy} if proxy else None

#         page_content = None
        
#         # Try requests first
#         try:
#             response = session.get(url, proxies=proxies, timeout=15)
#             if response.status_code == 200:
#                 page_content = response.content
#                 print(f"✅ Successfully fetched page {page} with requests")
#             else:
#                 print(f"[!] Requests failed with status {response.status_code}")
#         except Exception as e:
#             print(f"[!] Requests failed: {e}")
        
#         # If requests failed, try Selenium
#         if not page_content:
#             page_content = try_selenium_scrape(url)
#             if page_content:
#                 print(f"✅ Successfully fetched page {page} with Selenium")
        
#         if not page_content:
#             print(f"[!] Failed to fetch page {page}, skipping...")
#             continue

#         soup = BeautifulSoup(page_content, 'html.parser')
#         results = soup.find_all('div', {'data-component-type': 's-search-result'})
        
#         if not results:
#             print(f"[!] No products found on page {page}")
#             break
        
#         print(f"✅ Page {page} scraped with {len(results)} items.")
        
#         page_products = 0
#         for i, item in enumerate(results, 1):
#             print(f"\n[DEBUG] Processing item {i}/{len(results)}")
            
#             # Extract title using enhanced method
#             title = extract_title_from_item(item)
            
#             # Extract price using enhanced method
#             price = extract_price_from_item(item)
            
#             # Skip if we couldn't extract essential information
#             if not title or not price:
#                 print(f"[DEBUG] Skipping item {i}: title={bool(title)}, price={bool(price)}")
#                 continue
            
#             # Validate title length and content
#             if (len(title) < 10 or
#                 title.lower() in ['apple', 'samsung', 'xiaomi', 'oppo', 'vivo', 'realme', 'huawei'] or
#                 'stars' in title.lower() or
#                 'rating' in title.lower() or
#                 'details' in title.lower() or
#                 'see all' in title.lower() or
#                 title.replace('.', '').replace(' ', '').replace(',', '').isdigit()):
#                 print(f"[DEBUG] Skipping item {i}: Invalid title content")
#                 continue
            
#             # Check for duplicates
#             if title in seen_titles:
#                 print(f"[DEBUG] Skipping item {i}: Duplicate title")
#                 continue
#             seen_titles.add(title)

#             # Additional filtering for mobile category
#             if category_code == '21832883031':
#                 title_lower = title.lower()
#                 # Must contain phone-related keywords for mobile category
#                 phone_keywords = ['موبايل', 'mobile', 'phone', 'smartphone', 'ايفون', 'iphone', 'جالاكسي', 'galaxy', 'هاتف']
#                 if not any(keyword in title_lower for keyword in phone_keywords):
#                     print(f"[DEBUG] Skipping item {i}: Not a phone product")
#                     continue
                
#                 # Filter out accessories more strictly
#                 if is_accessory(title):
#                     print(f"[DEBUG] Skipping item {i}: Detected as accessory")
#                     continue

#             product = {
#                 'title': title,
#                 'price': price,
#                 'store': 'Amazon',
#                 'category': 'mobiles' if category_code == '21832883031' else 'other',
#                 'query': keyword
#             }

#             # Commented out the part related to Supabase since it's not needed right now
#             # supabase.table("products").upsert(product).execute()

#             all_products.append(product)
#             page_products += 1
#             print(f"[DEBUG] Added product {page_products}: {title[:50]}... - {price} EGP")
        
#         print(f"\n✅ Found {page_products} valid products on page {page}")
        
#         if page_products == 0:
#             print(f"[!] No valid products found on page {page}, stopping...")
#             break
    
#     print(f"\n✅ Found {len(all_products)} total products on Amazon for '{keyword}':")
#     print("-" * 80)
#     for i, product in enumerate(all_products, 1):
#         display_title = product['title'][:100] + "..." if len(product['title']) > 100 else product['title']
#         print(f"{i}. Price: {product['price']} EGP")
#         print(f"   Title: {display_title}")
#         print("-" * 80)

#     return all_products

# if __name__ == "__main__":
#     print("Available categories:")
#     for key in CATEGORY_MAPPING:
#         print(f"  {key}")

#     category_input = input("\nEnter category (or press Enter to skip): ").strip().lower()
#     category_code = CATEGORY_MAPPING.get(category_input) if category_input else None

#     keyword = input("Enter product to search: ").strip()
#     products = get_products_from_search(keyword, category_code)

#     if products:
#         print(f"\n🎉 Successfully found {len(products)} products!")
#     else:
#         print("\n❌ No products found or request was blocked.")
