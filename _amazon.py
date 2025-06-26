import requests
from bs4 import BeautifulSoup
import re
import time
import random
from supabase import create_client, Client  # NEW

# --- Supabase Setup ---
SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5obmJpemR3Y2Zvdnd4bWVwd210Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA5NTkzMzMsImV4cCI6MjA2NjUzNTMzM30.0Dmk33vYjiTCElh7rBY0JFelqUrEeKGQHf1uGIsUA10"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

USE_PROXY = False
PROXIES = [
    # Example proxies
]

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (Linux; Android 10; SM-G960F)",
    "Mozilla/5.0 (iPad; CPU OS 13_6 like Mac OS X)"
]

CATEGORY_MAPPING = {
    'phones': '21832883031',
    'mobile': '21832883031',
    'mobiles': '21832883031',
    'smartphone': '21832883031',
    'smartphones': '21832883031',
    'electronics': 'electronics',
    'computers': 'computers',
    'laptops': 'laptops',
    'tablets': 'tablets',
    'headphones': 'headphones',
    'watches': 'watches',
    'cameras': 'cameras'
}

ACCESSORY_KEYWORDS = [
    "case", "cover", "screen", "protector", "glass", "accessory", "charger", "cable", "headset",
    "جراب", "حافظة", "زجاج", "واقي", "شاحن", "كابل", "سماعة", "لاصقة"
]

def build_search_url(keyword, category_code=None):
    base_url = 'https://www.amazon.eg/s'
    params = {'k': keyword}
    if category_code and category_code.isdigit():
        params['rh'] = f'n:{category_code}'
    return requests.Request('GET', base_url, params=params).prepare().url

def get_products_from_search(keyword, category_code=None):
    url = build_search_url(keyword, category_code)

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com"
    }

    delay = random.uniform(4, 8)
    print(f"[+] Sleeping for {round(delay, 2)} seconds to avoid detection...")
    time.sleep(delay)

    session = requests.Session()
    session.headers.update(headers)
    session.cookies.clear()

    proxy = random.choice(PROXIES) if USE_PROXY else None
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = session.get(url, proxies=proxies, timeout=15)
    except Exception as e:
        print(f"[!] Request failed: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    results = soup.find_all('div', {'data-component-type': 's-search-result'})
    products = []

    for item in results:
        whole = item.find('span', {'class': 'a-price-whole'})
        fraction = item.find('span', {'class': 'a-price-fraction'})
        title_tag = item.find('h2')
        title_span = title_tag.find('span') if title_tag else None
        title = title_span.get_text(strip=True) if title_span else "No title found"

        if whole:
            full_price = f"{re.sub(r'[^\d]', '', whole.text)}.{fraction.text if fraction else '00'}"
            try:
                price = float(full_price)

                if category_code == '21832883031':
                    lowered = title.lower()
                    if any(keyword in lowered for keyword in ACCESSORY_KEYWORDS):
                        continue

                product = {
                    'title': title,
                    'price': price,
                    'store': 'Amazon',
                    'category': 'mobiles' if category_code == '21832883031' else 'other',
                    'query': keyword
                }

                # Push to Supabase
                supabase.table("products").upsert(product).execute()

                products.append(product)

            except ValueError:
                continue

    return products

if __name__ == "__main__":
    print("Available categories:")
    for key in CATEGORY_MAPPING:
        print(f"  {key}")

    category_input = input("\nEnter category (or press Enter to skip): ").strip().lower()
    category_code = CATEGORY_MAPPING.get(category_input) if category_input else None

    keyword = input("Enter product to search: ").strip()
    products = get_products_from_search(keyword, category_code)

    if products:
        print(f"\n✅ Found {len(products)} products for '{keyword}'" +
              (f" in category '{category_code}'" if category_code else "") + ":")
        print("-" * 80)
        for i, product in enumerate(products, 1):
            display_title = product['title'][:100] + "..." if len(product['title']) > 100 else product['title']
            print(f"{i}. Price: {product['price']} EGP")
            print(f"   Title: {display_title}")
            print("-" * 80)
    else:
        print("\n❌ No products found or request was blocked.")
