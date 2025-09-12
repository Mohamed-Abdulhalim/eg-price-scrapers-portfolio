from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import supabase
from supabase import create_client
import chromedriver_autoinstaller
import os, sys

chromedriver_autoinstaller.install()
ACCESSORY_KEYWORDS_AR = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا",
    "كارل"
]

ACCESSORY_KEYWORDS_EN = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger",
    "cable", "headset", "silicone", "bumper", "shell", "skin", "sleeve", "lens", "wallet"
]

# Supabase config

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"] # use service_role for writes
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY (set as Actions secrets and mapped in scrape.yml).")
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_accessory(title):
    title_lower = title.lower()
    for word in ACCESSORY_KEYWORDS_AR:
        if word in title_lower:
            return True
    for word in ACCESSORY_KEYWORDS_EN:
        if word in title_lower:
            return True
    return False

def extract_price(product_card):
    special = product_card.select_one(".special-price .price")
    if special:
        return special.text

    regular = product_card.select_one(".price")
    if regular:
        return regular.text

    return None

def search_2b(product_name, category=""):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    driver = webdriver.Chrome(options=options)

    print(f"[🔍] Searching 2B for: {product_name}")
    
    base_url = f"https://2b.com.eg/ar/catalogsearch/result/?q={product_name}"
    driver.get(base_url)
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    product_cards = soup.find_all("li", class_="item product product-item")
    all_products = []
    seen_titles = set()

    for card in product_cards:
        title_tag = card.find("a", class_="product-item-link")
        if not title_tag:
            continue
        title = title_tag.text.strip()

        if category.lower() == "mobiles" and is_accessory(title):
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)

        price_str = extract_price(card)
        if not price_str:
            continue

        price_str = price_str.replace("ج.م.‏", "").replace(",", "").replace("٬", "").replace("\u00a0", "").strip()
        try:
            price = float(price_str)
        except:
            price = 0.0

        product_data = {
            "store": "2B",
            "title": title,
            "price": price,
            "category": "mobiles" if category.lower() == "mobiles" else "other",
            "query": product_name
        }
        all_products.append(product_data)

        # Push to Supabase
        try:
            supabase_client.table("products").upsert(product_data).execute()
        except Exception as e:
            print(f"❌ Failed to upload product: {e}")

    driver.quit()

    print(f"\n✅ Found {len(all_products)} products on 2B for '{product_name}':")
    print("-" * 80)
    for i, product in enumerate(all_products, 1):
        print(f"{i}. السعر: {product['price']} جنيه")
        print(f"   الاسم: {product['title']}")
        print("-" * 80)

    return all_products

if __name__ == "__main__":
    product = input("🔎 اكتب اسم المنتج للبحث: ").strip()
    category = input("📂 اكتب الفئة (اكتب 'mobiles' إذا كنت تريد تجاهل الإكسسوارات): ").strip()
    search_2b(product, category)
