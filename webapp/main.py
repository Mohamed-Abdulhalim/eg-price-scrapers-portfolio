from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
import re

app = Flask(__name__)

SUPABASE_URL = "https://nhnbizdwcfovwxmepwmt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5obmJpemR3Y2Zvdnd4bWVwd210Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA5NTkzMzMsImV4cCI6MjA2NjUzNTMzM30.0Dmk33vYjiTCElh7rBY0JFelqUrEeKGQHf1uGIsUA10"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    # Fetch unique brands and suffixes for dropdowns
    brands_resp = supabase.table("products").select("brand_or_model").execute()
    suffixes_resp = supabase.table("products").select("suffix").execute()

    brands = brands_resp.data or []
    suffixes = suffixes_resp.data or []

    unique_brands = sorted({item['brand_or_model'] for item in brands if item['brand_or_model']})
    unique_suffixes = sorted({item['suffix'] for item in suffixes if item['suffix']})

    return render_template(
        "index.html",
        brands=unique_brands,
        suffixes=unique_suffixes
    )

@app.route('/get_models')
def get_models():
    brand = request.args.get('brand')
    if not brand:
        return jsonify([])

    response = supabase.table("products").select("model").eq("brand_or_model", brand).execute()
    models = sorted({item['model'] for item in response.data if item['model']})
    return jsonify(models)

@app.route('/get_suffixes')
def get_suffixes():
    brand = request.args.get('brand')
    if not brand:
        return jsonify([])

    response = supabase.table("products").select("suffix").eq("brand_or_model", brand).execute()
    suffixes = sorted({item['suffix'] for item in response.data if item['suffix']})
    return jsonify(suffixes)

@app.route('/search')
def search():
    brand = request.args.get("brand_or_model", "").strip()
    model = request.args.get("model", "").strip()
    suffix = request.args.get("suffix", "").strip()
    category = request.args.get("category", "").strip()

    query_builder = supabase.table("products").select("*")

    if brand:
        query_builder = query_builder.eq("brand_or_model", brand)
    if model:
        query_builder = query_builder.eq("model", model)
    if suffix:
        query_builder = query_builder.eq("suffix", suffix)
    if category:
        query_builder = query_builder.ilike("category", f"%{category}%")

    response = query_builder.execute()
    results = response.data or []

    return render_template("results.html", query=brand, results=results)

@app.route('/chat_ai', methods=['POST'])
def chat_ai():
    

    user_message = request.json.get("message", "")
    # TODO: Replace this with an actual LLM call
    # For now, let's parse manually for demo

    # Naive regex extraction (improve later with AI)
    phone_keywords = re.findall(r"(ايفون|سامسونج|شاومي|ريدمي|هواوي|ريلمي)", user_message, re.IGNORECASE)
    model_keywords = re.findall(r"\d{1,2}", user_message)
    suffix_keywords = re.findall(r"(برو ماكس|برو|بلس|ألترا)", user_message, re.IGNORECASE)
    wants_installment = "تقسيط" in user_message

    brand = phone_keywords[0] if phone_keywords else ""
    model = model_keywords[0] if model_keywords else ""
    suffix = suffix_keywords[0] if suffix_keywords else ""

    # Run search using your existing logic
    query = supabase.table("products").select("*")

    if brand:
        query = query.ilike("brand_or_model", f"%{brand}%")
    if model:
        query = query.ilike("model", f"%{model}%")
    if suffix:
        query = query.ilike("suffix", f"%{suffix}%")
    if wants_installment:
        query = query.neq("installment", None)  # Or whatever your installment column is

    results = query.execute().data or []

    if not results:
        return jsonify({"response": "معرفتش ألاقي الموبايل ده يا معلم، جرب تكتبلي اسم تاني 😉"})

    # Pick cheapest result
    sorted_results = sorted(results, key=lambda x: x.get("price", 1e9))
    top = sorted_results[0]

    response = f"بص يا معلم، أرخص {top['brand_or_model']} {top['model']} {top['suffix']} لقيته في {top['store']} بـ {top['price']} جنيه"
    if wants_installment and top.get("installment"):
        response += f" وتقسيطه {top['installment']}"

    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True)
