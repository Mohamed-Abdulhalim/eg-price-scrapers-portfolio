from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client

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

if __name__ == "__main__":
    app.run(debug=True)
