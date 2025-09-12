from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
from supabase import create_client, Client
import os, sys
import chromedriver_autoinstaller

chromedriver_autoinstaller.install()
# Supabase config

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # use service_role for writes
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY (set as Actions secrets and mapped in scrape.yml).")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ACCESSORY_KEYWORDS_AR = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
    "شاحن", "كابل", "سلك", "بطارية", "حقيبة", "محفظة", "جلد", "سيليكون",
    "اسكرين", "اسكرين بروتيكتور", "اسكرين جلاس", "باور بانك", "باور بانك",
    "سكرين", "آيفون 13 وآيفون 14", "آيفون 13 برو ماكس"
]

ACCESSORY_KEYWORDS_EN = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger",
    "cable", "headset", "silicone", "bumper", "shell", "skin", "sleeve", "lens", "wallet"
    "battery", "bag", "pouch", "leather", "silicone", "shockproof", "tempered glass",
    "power bank", "powerbank", "headphones", "earphones", "earbuds", "stylus", "stand",
    "tripod", "car mount", "holder", "adapter", "dock", "cradle", "wristband", "strap",
    "indicator", "remote", "keyboard", "mouse", "screen protector", "tempered glass",
    "wireless charger", "fast charger", "car charger", "USB cable", "lightning cable", "type-c cable", "aux cable",
    "HDMI cable", "OTG cable", "audio cable", "charging dock",
]

def is_accessory(title):
    title_lower = title.lower()
    return any(word in title_lower for word in ACCESSORY_KEYWORDS_AR + ACCESSORY_KEYWORDS_EN)

def search_btech_fixed(product_name, category=""):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    driver = webdriver.Chrome(options=options)

    print(f"[🔍] Searching B.TECH for: {product_name}")

    url = f"https://btech.com/ar/catalogsearch/result/?q={product_name}"
    driver.get(url)
    time.sleep(4)

    product_blocks = driver.find_elements(By.CSS_SELECTOR, "div.plpContentWrapper")

    all_products = []
    seen_titles = set()

    for block in product_blocks:
        try:
            title_el = block.find_element(By.CSS_SELECTOR, "h2.plpTitle")
            price_el = block.find_element(By.CSS_SELECTOR, "span.price-wrapper")

            title = title_el.text.strip()
            if not title or title in seen_titles:
                continue
            if category.lower() == "mobiles" and is_accessory(title):
                continue
            seen_titles.add(title)

            price_text = price_el.text.strip().replace(",", "").replace(" ", "")
            price = float(price_text)

            product_data = {
                "title": title,
                "price": price,
                "store": "B.TECH",
                "category": category,
                "query": product_name
            }

            all_products.append(product_data)

            supabase.table("products").upsert(product_data).execute()

        except Exception as e:
            continue

    driver.quit()

    print(f"\n✅ Found {len(all_products)} products on B.TECH for '{product_name}':")
    print("-" * 80)
    for i, product in enumerate(all_products, 1):
        print(f"{i}. السعر: {product['price']} جنيه")
        print(f"   الاسم: {product['title']}")
        print("-" * 80)

    return all_products

if __name__ == "__main__":
    product = input("🔎 اكتب اسم المنتج للبحث: ").strip()
    category = input("📂 اكتب الفئة (اكتب 'mobiles' إذا كنت تريد تجاهل الإكسسوارات): ").strip()
    search_btech_fixed(product, category)
