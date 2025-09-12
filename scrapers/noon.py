import requests
from bs4 import BeautifulSoup
import time
import random
import re
import csv
from supabase import create_client, Client

# ---------------- Supabase Setup ----------------
SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5obmJpemR3Y2Zvdnd4bWVwd210Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA5NTkzMzMsImV4cCI6MjA2NjUzNTMzM30.0Dmk33vYjiTCElh7rBY0JFelqUrEeKGQHf1uGIsUA10"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- Normalize Arabic ----------------
def normalize_arabic(text):
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"[ى]", "ي", text)
    text = re.sub(r"[ة]", "ه", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------- Accessory Filter ----------------
ACCESSORY_KEYWORDS = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
    "case", "cover", "protector", "glass", "lens", "bumper",
    "screen", "tpu", "silicone", "shock", "clear", "camera",
    "wallet", "flip", "back", "shell", "skin", "pouch", "armor"
]

def is_accessory(title):
    title_norm = normalize_arabic(title).lower()
    return any(keyword.lower() in title_norm for keyword in ACCESSORY_KEYWORDS)

# ---------------- Brand Detection ----------------
def extract_brand_or_model(title):
    title_norm = normalize_arabic(title.lower())

    if "ايباد" in title_norm or "ipad" in title_norm:
        return "ايباد"

    if ("ايفون" in title_norm or "iphone" in title_norm) and "كابل" not in title_norm:
        return "ايفون"

    if "ابل" in title_norm and ("iphone" in title_norm or "ايفون" in title_norm):
        return "ايفون"

    if "شاومي" in title_norm and ("ريدمي" in title_norm or "redmi" in title_norm):
        return "ريدمي"

    if "شاومي" in title_norm and ("poco" in title_norm or "بوكو" in title_norm):
        return "بوكو"

    if "بوكو" in title_norm or "poco" in title_norm:
        return "بوكو"

    if "ريدمي" in title_norm or "redmi" in title_norm:
        return "ريدمي"

    if "ريلمي" in title_norm or "ريل مي" in title_norm or "realme" in title_norm:
        return "ريلمي"

    if re.search(r"\bابل\b", title_norm) and "كابل" not in title_norm:
        return "Apple"

    brand_map = {
        "سامسونج": "سامسونج", "samsung": "Samsung",
        "هواوي": "هواوي", "huawei": "Huawei",
        "شاومي": "شاومي", "xiaomi": "Xiaomi",
        "اوبو": "اوبو", "oppo": "Oppo",
        "فيفو": "فيفو", "vivo": "Vivo",
        "نوكيا": "نوكيا", "nokia": "Nokia",
        "سوني": "سوني", "sony": "Sony",
        "جوجل": "جوجل", "google": "Google Pixel",
        "موتورولا": "موتورولا", "motorola": "Motorola",
        "ون بلس": "ون بلس", "oneplus": "OnePlus",
        "ال جي": "ال جي", "lg": "LG"
    }

    for keyword, brand in brand_map.items():
        if keyword in title_norm:
            return brand

    return "Unknown"

# ---------------- Model and Suffix Extraction ----------------
def extract_model_and_suffix(title):
    title = normalize_arabic(title)
    suffix = ""

    suffix_match = re.search(r"\b(pro\+?|برو)\b", title, re.IGNORECASE)
    if suffix_match:
        suffix = suffix_match.group(1).capitalize()

    model_match = re.search(r"(?:ريلمي|realme).*?(\d{2})", title, re.IGNORECASE)
    if model_match:
        model = model_match.group(1)
        return model, suffix

    fallback = re.search(r"\b([a-zA-Z]{1,2}\d{1,3}[a-zA-Z+]{0,4})\b", title, re.IGNORECASE)
    if fallback:
        return fallback.group(1).upper(), suffix

    return None, suffix

# ---------------- Scraper Settings ----------------
HEADERS = {
    "User-Agent": random.choice([
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (Linux; Android 10; SM-G960F)"
    ]),
    "Accept-Language": "ar-EG,ar;q=0.9"
}

def build_noon_ar_search_url(keyword):
    encoded = keyword.replace(" ", "%20")
    return f"https://www.noon.com/egypt-ar/search?q={encoded}"

# ---------------- Main Scraper ----------------
def get_noon_ar_products(keyword):
    url = build_noon_ar_search_url(keyword)
    print(f"[🔍] جاري البحث عن '{keyword}' في نون...")

    time.sleep(random.uniform(2, 5))

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')

        titles = soup.find_all("h2", {"class": "ProductDetailsSection_title__JorAV"})
        prices = soup.find_all("strong", {"class": "Price_amount__2sXa7"})

        products = []
        for title_tag, price_tag in zip(titles, prices):
            title = title_tag.text.strip()
            normalized_title = normalize_arabic(title)

            raw_price = price_tag.text.strip()
            clean_price = float(re.sub(r"[^\d.]", "", raw_price.replace(",", "")))

            if is_accessory(normalized_title):
                continue

            brand = extract_brand_or_model(normalized_title)
            model, suffix = extract_model_and_suffix(normalized_title)

            product = {
                "store": "noon",
                "title": normalized_title,
                "price": clean_price,
                "category": "mobiles",
                "query": keyword,
                "brand_or_model": brand,
                "model": model,
                "suffix": suffix
            }

            try:
                supabase.table("products").insert(product).execute()
                print(f"✅ Uploaded: {title[:40]}... - {clean_price} EGP")
            except Exception as e:
                print(f"[!] Supabase insert failed: {e}")

            products.append(product)

        return products

    except Exception as e:
        print(f"[❌] خطأ أثناء جلب البيانات: {e}")
        return []

# ---------------- Main Runner ----------------
if __name__ == "__main__":
    keywords = [
        "iphone", "samsung", "xiaomi", "oppo", "huawei",
        "realme", "vivo", "oneplus", "poco", "nokia", "sony", "lg"
    ]

    all_products = []

    for keyword in keywords:
        print(f"\n=== 🔎 البحث عن: {keyword} ===")
        products = get_noon_ar_products(keyword)
        all_products.extend(products)

    print(f"\n✅ Total products uploaded: {len(all_products)}")




















# from matplotlib.pyplot import title
# import requests
# from bs4 import BeautifulSoup
# import time
# import random
# import re
# import csv

# # ---------------- Normalize Arabic ----------------
# def normalize_arabic(text):
#     text = re.sub(r"[إأآا]", "ا", text)
#     text = re.sub(r"[ى]", "ي", text)
#     text = re.sub(r"[ة]", "ه", text)
#     text = re.sub(r"\s+", " ", text)
#     return text.strip()

# # ---------------- Accessory Filter ----------------
# ACCESSORY_KEYWORDS = [
#     "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
#     "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
#     "case", "cover", "protector", "glass", "lens", "bumper",
#     "screen", "tpu", "silicone", "shock", "clear", "camera",
#     "wallet", "flip", "back", "shell", "skin", "pouch", "armor"
# ]

# def is_accessory(title):
#     title_norm = normalize_arabic(title).lower()
#     return any(keyword.lower() in title_norm for keyword in ACCESSORY_KEYWORDS)

# # ---------------- Brand Detection ----------------
# def extract_brand_or_model(title):
#     title_norm = normalize_arabic(title.lower())

#     if "ايباد" in title_norm or "ipad" in title_norm:
#         return "ايباد"

#     if ("ايفون" in title_norm or "iphone" in title_norm) and "كابل" not in title_norm:
#         return "ايفون"

#     if "ابل" in title_norm and ("iphone" in title_norm or "ايفون" in title_norm):
#         return "ايفون"

#     if "شاومي" in title_norm and ("ريدمي" in title_norm or "redmi" in title_norm):
#         return "ريدمي"

#     if "شاومي" in title_norm and ("poco" in title_norm or "بوكو" in title_norm):
#         return "بوكو"

#     if "بوكو" in title_norm or "poco" in title_norm:
#         return "بوكو"

#     if "ريدمي" in title_norm or "redmi" in title_norm:
#         return "ريدمي"

#     if "ريلمي" in title_norm or "ريل مي" in title_norm or "realme" in title_norm:
#         return "ريلمي"

#     if re.search(r"\bابل\b", title_norm) and "كابل" not in title_norm:
#         return "Apple"

#     brand_map = {
#         "سامسونج": "سامسونج", "samsung": "Samsung",
#         "هواوي": "هواوي", "huawei": "Huawei",
#         "شاومي": "شاومي", "xiaomi": "Xiaomi",
#         "اوبو": "اوبو", "oppo": "Oppo",
#         "فيفو": "فيفو", "vivo": "Vivo",
#         "نوكيا": "نوكيا", "nokia": "Nokia",
#         "سوني": "سوني", "sony": "Sony",
#         "جوجل": "جوجل", "google": "Google Pixel",
#         "موتورولا": "موتورولا", "motorola": "Motorola",
#         "ون بلس": "ون بلس", "oneplus": "OnePlus",
#         "ال جي": "ال جي", "lg": "LG"
#     }

#     for keyword, brand in brand_map.items():
#         if keyword in title_norm:
#             return brand

#     return "Unknown"

# # ---------------- Model and Suffix Extraction ----------------
# def extract_model_and_suffix(title):
#     title = normalize_arabic(title)
#     suffix = ""

#     # Detect suffix like برو / Pro
#     suffix_match = re.search(r"\b(pro|برو)\b", title, re.IGNORECASE)
#     if suffix_match:
#         suffix = suffix_match.group(1).capitalize()

#     # iPhone: "ايفون 16" or "iphone 13"
#     iphone_match = re.search(r"(?:ايفون|iphone)\s*(\d{1,3})", title, re.IGNORECASE)
#     if iphone_match:
#         return iphone_match.group(1), suffix

#     # Samsung: Z Fold / Flip
#     z_series = re.search(r"z\s*(fold|flip)\s*(\d{1,2})", title, re.IGNORECASE)
#     if z_series:
#         return f"Z {z_series.group(1).capitalize()} {z_series.group(2)}", suffix

#     # Redmi Note 13 Pro+ → Note13
#     note = re.search(r"(?:note|نوت)\s*(\d{1,2})", title, re.IGNORECASE)
#     if note:
#         return f"Note{note.group(1)}", "نوت" if not suffix else suffix

#     # Redmi 13C / 14C → 13C, 14C
#     redmi_c = re.search(r"\b(?:ريدمي|redmi)\s*(\d{1,2}c)\b", title, re.IGNORECASE)
#     if redmi_c:
#         return redmi_c.group(1).upper(), suffix

#     # Redmi plain number (Redmi 13) → 13
#     redmi_plain = re.search(r"\b(?:ريدمي|redmi)\s*(\d{1,2})\b", title, re.IGNORECASE)
#     if redmi_plain:
#         return redmi_plain.group(1), suffix

#     # Oppo Reno 12F, 12 Pro, 6, 8T
#     oppo_reno_f = re.search(r"reno\s*(\d{1,2}f)\b", title, re.IGNORECASE)
#     if oppo_reno_f:
#         return oppo_reno_f.group(1).upper(), suffix

#     oppo_reno_t = re.search(r"reno\s*(\d{1,2}t)\b", title, re.IGNORECASE)
#     if oppo_reno_t:
#         return oppo_reno_t.group(1).upper(), suffix

#         # Oppo Reno 12, 12 Pro, etc. — flexible spacing & variants
#     oppo_reno_number = re.search(r"reno\s*(\d{1,2})(?:\s*pro\+?)?", title, re.IGNORECASE)
#     if oppo_reno_number:
#         return oppo_reno_number.group(1), suffix

#         # Realme direct models: ريل مي 14، 14T، 14 Pro, etc.
#     realme_direct_model = re.search(r"(?:ريلمي|realme)\s*(14t|14\s*pro\+?|14)", title, re.IGNORECASE)
#     if realme_direct_model:
#         return realme_direct_model.group(1).replace(" ", "").upper(), suffix
#     # Explicit Realme 14 match (14, 14 Pro, 14T, etc.)
#     realme_14 = re.search(r"\b(?:ريلمي|realme)[^0-9]{0,15}14(?:\s*pro\+?|t)?", title, re.IGNORECASE)
#     if realme_14:
#         return "14", suffix

#     # Realme: 12, 14, 14 Pro, 12 Pro+, etc.
#     # Realme: e.g., "ريل مي هاتف 12 Pro+", "realme 14 pro+"
#     realme_match = re.search(r"(?:ريلمي|realme).*?(\d{2})(?:\s*pro\+?)?", title, re.IGNORECASE)
#     if realme_match:
#         model_str = realme_match.group(1).strip()
#     # If Pro+ is included, set suffix
#         if re.search(r"pro\+?", title, re.IGNORECASE):
#             suffix = "Pro+"
#         return model_str, suffix

#     # OnePlus Nord CE 3 → CE3
#     oneplus_nord_ce = re.search(r"nord\s*ce\s*(\d{1,2})", title, re.IGNORECASE)
#     if oneplus_nord_ce:
#         return f"CE{oneplus_nord_ce.group(1)}", suffix

#     # OnePlus Nord 4 → نورد 4 (support both Arabic and English)
#     nord_4_match = re.search(r"(?:nord|نورد)\s*4", title, re.IGNORECASE)
#     if nord_4_match:
#         return "نورد 4", suffix


#     # OnePlus numbered (e.g. ون بلس 13)
#     oneplus_num = re.search(r"(?:ون بلس|oneplus)\s*(\d{1,2})", title, re.IGNORECASE)
#     if oneplus_num:
#         return oneplus_num.group(1), suffix

#     # Samsung A-series
#     a_series = re.search(r"\bايه\s*(\d{1,3})\b", title)
#     if a_series:
#         return f"A{a_series.group(1)}", suffix

#     # Realme C-series: C75, C75X, C63
#     c_model = re.search(r"\b([cn]\d{2}[x+]?)\b", title.lower())
#     if c_model:
#         return c_model.group(1).upper(), suffix

#     # Nokia classic models
#     nokia_models = re.search(r"\b(105|106|130|150|216|2720|5310|5710|6310)\b", title)
#     if nokia_models:
#         return nokia_models.group(1), suffix

#     # Fallback: S23, X6 Pro, 13 Pro, etc.
#     fallback = re.search(r"\b([a-zA-Z]{1,2}\d{1,3}[a-zA-Z+]{0,4})\b", title, re.IGNORECASE)
#     if fallback:
#         return fallback.group(1).upper(), suffix

#     return None, suffix

# # ---------------- Scraper Settings ----------------
# HEADERS = {
#     "User-Agent": random.choice([
#         "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
#         "Mozilla/5.0 (Linux; Android 10; SM-G960F)"
#     ]),
#     "Accept-Language": "ar-EG,ar;q=0.9"
# }

# def build_noon_ar_search_url(keyword):
#     encoded = keyword.replace(" ", "%20")
#     return f"https://www.noon.com/egypt-ar/search?q={encoded}"

# # ---------------- Main Scraper ----------------
# def get_noon_ar_products(keyword):
#     url = build_noon_ar_search_url(keyword)
#     print(f"[🔍] جاري البحث عن '{keyword}' في نون...")

#     time.sleep(random.uniform(2, 5))

#     try:
#         response = requests.get(url, headers=HEADERS, timeout=15)
#         soup = BeautifulSoup(response.content, 'html.parser')

#         titles = soup.find_all("h2", {"class": "ProductDetailsSection_title__JorAV"})
#         prices = soup.find_all("strong", {"class": "Price_amount__2sXa7"})

#         products = []
#         for title_tag, price_tag in zip(titles, prices):
#             title = title_tag.text.strip()
#             normalized_title = normalize_arabic(title)

#             raw_price = price_tag.text.strip()
#             clean_price = float(re.sub(r"[^\d.]", "", raw_price.replace(",", "")))

#             if is_accessory(normalized_title):
#                 continue

#             brand = extract_brand_or_model(normalized_title)
#             model, suffix = extract_model_and_suffix(normalized_title)

#             product = {
#                 "store": "noon",
#                 "title": normalized_title,
#                 "price": clean_price,
#                 "category": "mobiles",
#                 "query": keyword,
#                 "brand_or_model": brand,
#                 "model": model,
#                 "suffix": suffix
#             }

#             products.append(product)

#         return products

#     except Exception as e:
#         print(f"[❌] خطأ أثناء جلب البيانات: {e}")
#         return []

# # ---------------- Main Runner ----------------
# if __name__ == "__main__":
#     keywords = [
#         "iphone", "samsung", "xiaomi", "oppo", "huawei",
#         "realme", "vivo", "oneplus", "poco", "nokia", "sony", "lg"
#     ]

#     all_products = []

#     for keyword in keywords:
#         print(f"\n=== 🔎 البحث عن: {keyword} ===")
#         products = get_noon_ar_products(keyword)
#         all_products.extend(products)

#     if all_products:
#         filename = "noon_phone_results.csv"
#         with open(filename, mode='w', newline='', encoding='utf-8-sig') as file:
#             writer = csv.DictWriter(file, fieldnames=all_products[0].keys())
#             writer.writeheader()
#             writer.writerows(all_products)
#         print(f"\n💾 تم حفظ {len(all_products)} منتجًا في {filename}")
#     else:
#         print("\n❌ لم يتم العثور على أي منتجات.")
