from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
from supabase import create_client, Client
import os

chromedriver_autoinstaller.install()
# Supabase config
SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5obmJpemR3Y2Zvdnd4bWVwd210Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA5NTkzMzMsImV4cCI6MjA2NjUzNTMzM30.0Dmk33vYjiTCElh7rBY0JFelqUrEeKGQHf1uGIsUA10"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def normalize_arabic(text):
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"[ى]", "ي", text)
    text = re.sub(r"[ة]", "ه", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

ACCESSORY_KEYWORDS_AR = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
    "شاحن", "كابل", "سلك", "بطارية", "حقيبة", "محفظة", "جلد", "سيليكون",
    "اسكرين", "اسكرين بروتيكتور", "اسكرين جلاس", "باور بانك", "سكرين",
    "ايفون 13 وايفون 14", "ايفون 13 برو ماكس"
]

ACCESSORY_KEYWORDS_EN = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger",
    "cable", "headset", "silicone", "bumper", "shell", "skin", "sleeve", "lens", "wallet",
    "battery", "bag", "pouch", "leather", "shockproof", "tempered glass",
    "power bank", "powerbank", "headphones", "earphones", "earbuds", "stylus", "stand",
    "tripod", "car mount", "holder", "adapter", "dock", "cradle", "wristband", "strap",
    "indicator", "remote", "keyboard", "mouse", "screen protector",
    "wireless charger", "fast charger", "car charger", "usb cable", "lightning cable",
    "type-c cable", "aux cable", "hdmi cable", "otg cable", "audio cable", "charging dock"
]

def is_accessory(title):
    title_norm = normalize_arabic(title).lower()
    title_lower = title.lower()

    normalized_keywords_ar = [normalize_arabic(word).lower() for word in ACCESSORY_KEYWORDS_AR]
    normalized_keywords_en = [word.lower() for word in ACCESSORY_KEYWORDS_EN]

    for word in normalized_keywords_ar:
        if word in title_norm:
            return True

    for word in normalized_keywords_en:
        if word in title_lower:
            return True

    return False

def search_jumia_fast(product_name, category=""):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    driver = webdriver.Chrome(options=options)

    print(f"[🔍] Searching Jumia for: {product_name}")

    all_products = []
    seen_titles = set()
    base_url = f"https://www.jumia.com.eg/ar/catalog/?q={product_name}"
    page = 1

    while True:
        url = f"{base_url}&page={page}"
        driver.get(url)
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        product_names = soup.find_all("h3", class_="name")
        product_prices = soup.find_all("div", class_="prc")

        if not product_names or len(product_prices) < 5:
            break

        print(f"✅ Page {page} scraped with {len(product_names)} items.")

        for i in range(min(len(product_names), len(product_prices))):
            title = product_names[i].text.strip()

            if category.lower() == "mobiles" and is_accessory(title):
                continue

            if title in seen_titles:
                continue
            seen_titles.add(title)

            price_str = product_prices[i].text.strip().replace("جنيه", "").replace(",", "").replace(" ", "")
            try:
                price = float(price_str)
            except:
                price = 0.0

            all_products.append({
                "title": title,
                "price": price
            })

        page += 1

    driver.quit()

    print(f"\n✅ Found {len(all_products)} total products on Jumia for '{product_name}':")
    print("-" * 80)
    for i, product in enumerate(all_products, 1):
        print(f"{i}. السعر: {product['price']} جنيه")
        print(f"   الاسم: {product['title']}")
        print("-" * 80)

    # Upload to Supabase
    if all_products:
        data_to_insert = [{
            "store": "jumia",
            "title": p["title"],
            "price": p["price"],
            "category": category,
            "query": product_name
        } for p in all_products]

        supabase.table("products").upsert(data_to_insert).execute()
        print("📤 Uploaded to Supabase!")

    return all_products

if __name__ == "__main__":
    product = input("🔎 اكتب اسم المنتج للبحث: ").strip()
    category = input("📂 اكتب الفئة (اكتب 'mobiles' إذا كنت تريد تجاهل الإكسسوارات): ").strip()
    search_jumia_fast(product, category)
