from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import os, sys

# Supabase
from supabase import create_client, Client

# optional; fine to leave
import chromedriver_autoinstaller
chromedriver_autoinstaller.install()

ACCESSORY_KEYWORDS_AR = [
    "جراب", "كفر", "حماية", "غطاء", "لاصقة", "شاشة", "واقي",
    "سماعة", "سماعات", "قلم", "عدسة", "حافظة", "غطى", "كاميرا", "كارل"
]
ACCESSORY_KEYWORDS_EN = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger",
    "cable", "headset", "silicone", "bumper", "shell", "skin", "sleeve", "lens", "wallet"
]

# ── Supabase config via env (from GitHub Actions secrets) ───────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().strip('"').strip("'")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
             "Set repo secrets and map them in your workflow env.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Helpers ────────────────────────────────────────────────────────────────────
def is_accessory(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in ACCESSORY_KEYWORDS_AR) or any(w in t for w in ACCESSORY_KEYWORDS_EN)

def extract_price(product_card):
    special = product_card.select_one(".special-price .price")
    if special:
        return special.text
    regular = product_card.select_one(".price")
    if regular:
        return regular.text
    return None

# ── Main scraper ───────────────────────────────────────────────────────────────
def search_2b(product_name, category=""):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
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

        price_str = (
            price_str.replace("ج.م.‏", "")
                     .replace("ج.م", "")
                     .replace(",", "")
                     .replace("٬", "")
                     .replace("\u00a0", "")
                     .strip()
        )
        try:
            price = float(price_str)
        except Exception:
            price = 0.0

        product_data = {
            "store": "2B",
            "title": title,
            "price": price,
            "category": "mobiles" if category.lower() == "mobiles" else "other",
            "query": product_name
        }
        all_products.append(product_data)

        # Push to Supabase (use the SAME variable name we created above)
        try:
            supabase.table("products").upsert(product_data).execute()
            print(f"✅ Uploaded: {title[:60]} ... {price}")
        except Exception as e:
            print(f"❌ Failed to upload product: {e}")

    driver.quit()

    print(f"\n✅ Found {len(all_products)} products on 2B for '{product_name}':")
    return all_products

if __name__ == "__main__":
    # In Actions we pipe input; locally you can type it
    product = input("🔎 اكتب اسم المنتج للبحث: ").strip()
    category = input("📂 اكتب الفئة (اكتب 'mobiles' إذا كنت تريد تجاهل الإكسسوارات): ").strip()
    search_2b(product, category)
