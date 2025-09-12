# Egypt E-Commerce Price Scrapers

This project maintains **5 production scrapers** running daily via GitHub Actions, pushing fresh data into a Supabase database.

### Target Stores
- Noon
- Amazon Egypt
- B.TECH
- 2B
- Jumia

### Features
- Extracts product name, price, availability, URL
- Normalizes brand + model names across stores
- Daily schedules (GitHub Actions + retry/backoff)
- Data stored in Supabase (Postgres + REST API)
- Sample dataset included (`samples/products.csv`)

### Tech
- Python (requests, bs4, selenium where needed)
- GitHub Actions
- Supabase (Postgres, Row-Level Security, API)

### Workflow Status
[![Run scrapers daily](https://github.com/Mohamed-Abdulhalim/eg-price-scrapers-portfolio/actions/workflows/scrape.yaml/badge.svg)](https://github.com/Mohamed-Abdulhalim/eg-price-scrapers-portfolio/actions/workflows/scrape.yaml)

### Demo
- See sample dataset: [products.csv](samples/products.csv)
- Screenshots in `/screenshots`

### How It Works
1. GitHub Actions runs scrapers daily at 02:00 Cairo time
2. Each scraper writes results into Supabase via REST API
3. Tables updated with idempotent upserts (no duplicates)
4. Clients consume via CSV download, API, or dashboards

### Use Cases
- Price monitoring
- Competitor analysis
- Automated data feeds for e-commerce

---
🚀 **Need scrapers or price dashboards?**  
I build reliable pipelines like this one, fully automated and production-ready.
