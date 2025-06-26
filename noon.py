import requests
from bs4 import BeautifulSoup
import time
import random
import re
from supabase import create_client, Client

# 🔌 Supabase config
SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5obmJpemR3Y2Zvdnd4bWVwd210Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA5NTkzMzMsImV4cCI6MjA2NjUzNTMzM30.0Dmk33vYjiTCElh7rBY0JFelqUrEeKGQHf1uGIsUA10"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Accessory keywords
ACCESSORY_KEYWORDS = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
    "case", "cover", "protector", "glass", "lens", "bumper",
    "screen", "tpu", "silicone", "shock", "clear", "camera",
    "wallet", "flip", "back", "shell", "skin", "pouch", "armor"
]

def is_accessory(title):
    lower_title = title.lower()
    return any(keyword.lower() in lower_title for keyword in ACCESSORY_KEYWORDS)

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

def get_noon_ar_products(keyword, filter_accessories=False):
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
            raw_price = price_tag.text.strip()
            clean_price = float(re.sub(r"[^\d.]", "", raw_price.replace(",", "")))

            if filter_accessories and is_accessory(title):
                continue

            product = {
                "store": "noon",
                "title": title,
                "price": clean_price,
                "category": "mobiles" if filter_accessories else "accessories",
                "query": keyword
            }

            products.append(product)

            # Save to Supabase
            supabase.table("products").insert(product).execute()

        return products

    except Exception as e:
        print(f"[❌] خطأ أثناء جلب البيانات: {e}")
        return []

if __name__ == "__main__":
    keyword = input("🔎 اكتب اسم المنتج للبحث: ").strip()
    category = input("📂 اكتب الفئة (اكتب 'mobiles' إذا كنت تريد تجاهل الإكسسوارات): ").strip().lower()
    apply_filter = category in ['mobile', 'mobiles', 'موبايل', 'موبايلات']

    products = get_noon_ar_products(keyword, filter_accessories=apply_filter)

    if products:
        print(f"\n✅ تم العثور على {len(products)} منتج من نون لكلمة '{keyword}':")
        print("-" * 80)
        for i, product in enumerate(products, 1):
            print(f"{i}. السعر: {product['price']} جنيه")
            print(f"   الاسم: {product['title']}")
            print("-" * 80)
    else:
        print("\n❌ لم يتم العثور على نتائج أو تم حظر الطلب.")
