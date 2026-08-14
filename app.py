from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from scraper import search_products, search_products_ranked
from deep_translator import GoogleTranslator
from models import init_db, get_db
from urllib.parse import urlparse, unquote
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import re

load_dotenv()  # reads .env in the project root and loads SECRET_KEY etc. into os.environ

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is not set. Create a .env file in the project root with a line like:\n"
        "SECRET_KEY=<a long random string>\n"
        "(run: python -c \"import secrets; print(secrets.token_hex(32))\" to generate one)"
    )
init_db()

# ---------------------------------------------------------------------------
# Human-friendly timestamps ("Today 8:50 AM", "Yesterday 3:12 PM", or a
# date for anything older) for saved products, compare list, collections.
# SQLite's datetime('now') stores UTC — converted to IST (+5:30) for display.
# ---------------------------------------------------------------------------
IST_OFFSET = timedelta(hours=5, minutes=30)


def format_relative_time(dt_str):
    if not dt_str:
        return ""
    try:
        dt_utc = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str

    dt_ist = dt_utc + IST_OFFSET
    now_ist = datetime.utcnow() + IST_OFFSET
    today = now_ist.date()
    yesterday = today - timedelta(days=1)

    time_str = dt_ist.strftime("%I:%M %p").lstrip("0")

    if dt_ist.date() == today:
        return f"Today {time_str}"
    elif dt_ist.date() == yesterday:
        return f"Yesterday {time_str}"
    else:
        return dt_ist.strftime("%b %d, %Y")


app.jinja_env.filters["relative_time"] = format_relative_time

# =============================================================================
# CATEGORY EXPANSION — every dict below keeps its ORIGINAL entries exactly
# as they were (same keys, same labels, same brand/query strings). Only NEW
# subcategory keys were appended at the end of each dict. New keys are named
# to match scraper.py's SUBCATEGORY_RULES keys 1:1 (see scraper.py — new
# rules were added there, plus a few alias entries — "covers", "powerbanks",
# "cables", "footwear", "staples", "dairy", "snacks" — for the subcategory
# keys that already existed here before this update) so no translation
# table is needed between app.py's sub_key and scraper.py's subcategory.
# No layout/UI template changes — same {label, brands: {...}} shape.
# =============================================================================
ELECTRONICS_SUBCATEGORIES = {
    "mobiles": {"label": "📱 Mobiles", "brands": {
        "Apple": "Apple iPhone", "Samsung": "Samsung Galaxy", "OnePlus": "OnePlus phone",
        "Vivo": "Vivo phone", "Oppo": "Oppo phone", "Xiaomi": "Xiaomi Redmi",
    }},
    "laptops": {"label": "💻 Laptops", "brands": {
        "HP": "HP laptop", "Dell": "Dell laptop", "Asus": "Asus laptop",
        "Lenovo": "Lenovo laptop", "Acer": "Acer laptop", "MacBook": "Apple MacBook",
    }},
    "tvs": {"label": "📺 TVs", "brands": {
        "Samsung": "Samsung Smart TV", "LG": "LG Smart TV", "Sony": "Sony Bravia TV",
        "Mi": "Mi Smart TV", "OnePlus": "OnePlus TV",
    }},
    "refrigerators": {"label": "❄️ Refrigerators", "brands": {
        "Samsung": "Samsung Refrigerator", "LG": "LG Refrigerator", "Whirlpool": "Whirlpool Refrigerator",
        "Haier": "Haier Refrigerator", "Godrej": "Godrej Refrigerator",
    }},
    "ac": {"label": "❄️ Air Conditioners", "brands": {
        "Samsung": "Samsung Air Conditioner", "LG": "LG Air Conditioner", "Voltas": "Voltas Air Conditioner",
        "Daikin": "Daikin Air Conditioner", "Blue Star": "Blue Star Air Conditioner",
    }},
    "monitors": {"label": "🖥️ Monitors", "brands": {
        "Dell": "Dell Monitor", "Samsung": "Samsung Monitor", "LG": "LG Monitor", "BenQ": "BenQ Monitor",
    }},
    "watches": {"label": "⌚ Smart Watches", "brands": {
        "Apple": "Apple Watch", "Samsung": "Samsung Galaxy Watch", "Noise": "Noise Smartwatch", "Fire-Boltt": "Fire-Boltt Smartwatch",
    }},
    "cameras": {"label": "📷 Cameras", "brands": {
        "Canon": "Canon Camera", "Nikon": "Nikon Camera", "Sony": "Sony Camera", "GoPro": "GoPro Camera",
    }},
    "gaming": {"label": "🎮 Gaming", "brands": {
        "PlayStation": "PlayStation 5", "Xbox": "Xbox Series", "Nintendo": "Nintendo Switch",
    }},
    "audio": {"label": "🎧 Audio", "brands": {
        "boAt": "boAt earphones", "JBL": "JBL speaker", "Sony": "Sony headphones", "Boult": "Boult earbuds",
    }},
    # ---- NEW electronics subcategories ----
    "tablets": {"label": "📱 Tablets", "brands": {
        "Apple": "Apple iPad", "Samsung": "Samsung Galaxy Tab", "Lenovo": "Lenovo Tab", "Xiaomi": "Xiaomi Pad",
    }},
    "washing_machines": {"label": "🧺 Washing Machines", "brands": {
        "Samsung": "Samsung Washing Machine", "LG": "LG Washing Machine",
        "Whirlpool": "Whirlpool Washing Machine", "IFB": "IFB Washing Machine",
    }},
    "printers": {"label": "🖨️ Printers", "brands": {
        "HP": "HP Printer", "Canon": "Canon Printer", "Epson": "Epson Printer",
    }},
    "networking": {"label": "📶 Networking", "brands": {
        "TP-Link": "TP-Link Router", "Netgear": "Netgear Router", "D-Link": "D-Link Router",
    }},
    "computer_components": {"label": "🖥️ Computer Components", "brands": {
        "NVIDIA": "NVIDIA Graphics Card", "AMD": "AMD Graphics Card", "Corsair": "Corsair RAM",
    }},
}

ACCESSORY_SUBCATEGORIES = {
    "covers": {"label": "📱 Mobile Covers", "brands": {
        "Apple": "Apple iPhone cover", "Samsung": "Samsung mobile cover", "Generic": "mobile cover",
    }},
    "chargers": {"label": "🔌 Chargers", "brands": {
        "Apple": "Apple charger", "Samsung": "Samsung charger", "Fast Charger": "fast charger",
    }},
    "powerbanks": {"label": "🔋 Power Banks", "brands": {
        "Mi": "Mi power bank", "boAt": "boAt power bank", "Ambrane": "Ambrane power bank",
    }},
    "cables": {"label": "🔗 Cables", "brands": {
        "USB-C": "USB Type C cable", "Lightning": "iPhone lightning cable", "HDMI": "HDMI cable",
    }},
    # ---- NEW electronics-accessories subcategories ----
    "earphones": {"label": "🎧 Earphones", "brands": {
        "boAt": "boAt earphones", "Realme": "Realme earphones", "JBL": "JBL earphones",
    }},
    "headphones": {"label": "🎧 Headphones", "brands": {
        "Sony": "Sony headphones", "boAt": "boAt headphones", "JBL": "JBL headphones",
    }},
    "tws_earbuds": {"label": "🎧 TWS Earbuds", "brands": {
        "boAt": "boAt TWS earbuds", "Apple": "Apple AirPods", "Noise": "Noise TWS earbuds",
    }},
    "bluetooth_speakers": {"label": "🔊 Bluetooth Speakers", "brands": {
        "JBL": "JBL Bluetooth speaker", "boAt": "boAt Bluetooth speaker", "Sony": "Sony Bluetooth speaker",
    }},
    "laptop_bags": {"label": "🎒 Laptop Bags", "brands": {
        "American Tourister": "American Tourister laptop bag", "HP": "HP laptop bag", "Dell": "Dell laptop bag",
    }},
    "mouse": {"label": "🖱️ Mouse", "brands": {
        "Logitech": "Logitech mouse", "HP": "HP wireless mouse", "Dell": "Dell mouse",
    }},
    "keyboards": {"label": "⌨️ Keyboards", "brands": {
        "Logitech": "Logitech keyboard", "HP": "HP keyboard", "Dell": "Dell keyboard",
    }},
    "webcams": {"label": "📷 Webcams", "brands": {
        "Logitech": "Logitech webcam", "HP": "HP webcam",
    }},
    "hdmi_cables": {"label": "🔗 HDMI Cables", "brands": {
        "Generic": "HDMI cable", "Amazon Basics": "Amazon Basics HDMI cable",
    }},
    "memory_cards": {"label": "💾 Memory Cards", "brands": {
        "SanDisk": "SanDisk memory card", "Samsung": "Samsung memory card",
    }},
    "pen_drives": {"label": "💾 Pen Drives", "brands": {
        "SanDisk": "SanDisk pen drive", "HP": "HP pen drive",
    }},
    "ssd_hdd": {"label": "💽 SSD / HDD", "brands": {
        "Samsung": "Samsung SSD", "WD": "WD hard disk", "Seagate": "Seagate hard disk",
    }},
    "power_strips": {"label": "🔌 Power Strips", "brands": {
        "Generic": "power strip extension board",
    }},
    "smart_home_accessories": {"label": "🏠 Smart Home", "brands": {
        "Amazon": "Amazon Echo smart speaker", "Mi": "Mi smart plug", "Google": "Google smart home",
    }},
}

CLOTHES_SUBCATEGORIES = {
    "men": {"label": "👔 Men", "brands": {
        "Shirts": "shirts for men", "Jeans": "jeans for men", "T-Shirts": "tshirts for men",
    }},
    "women": {"label": "👗 Women", "brands": {
        "Dresses": "dresses for women", "Kurtis": "kurtis for women", "Sarees": "sarees",
    }},
    "footwear": {"label": "👟 Footwear", "brands": {
        "Sneakers": "sneakers", "Sandals": "sandals", "Formal Shoes": "formal shoes",
    }},
    # ---- NEW fashion subcategories ----
    "kids": {"label": "🧒 Kids", "brands": {
        "Boys": "kids clothing boys", "Girls": "kids clothing girls",
    }},
    "tshirts": {"label": "👕 T-Shirts", "brands": {
        "Nike": "Nike t-shirt", "Adidas": "Adidas t-shirt", "Puma": "Puma t-shirt",
    }},
    "shirts": {"label": "👔 Shirts", "brands": {
        "Van Heusen": "Van Heusen shirt", "Peter England": "Peter England shirt", "Allen Solly": "Allen Solly shirt",
    }},
    "jeans": {"label": "👖 Jeans", "brands": {
        "Levis": "Levis jeans", "Wrangler": "Wrangler jeans", "Pepe Jeans": "Pepe jeans",
    }},
    "trousers": {"label": "👖 Trousers", "brands": {
        "Van Heusen": "Van Heusen trousers", "Peter England": "Peter England trousers",
    }},
    "dresses": {"label": "👗 Dresses", "brands": {
        "Zara": "Zara dress", "H&M": "H&M dress", "Vero Moda": "Vero Moda dress",
    }},
    "sarees": {"label": "🥻 Sarees", "brands": {
        "Silk": "silk saree", "Cotton": "cotton saree", "Banarasi": "Banarasi saree",
    }},
    "kurtis": {"label": "👚 Kurtis", "brands": {
        "Biba": "Biba kurti", "W": "W kurti", "Global Desi": "Global Desi kurti",
    }},
    "ethnic_wear": {"label": "🪔 Ethnic Wear", "brands": {
        "Manyavar": "Manyavar kurta", "Biba": "Biba ethnic wear", "Fabindia": "Fabindia ethnic wear",
    }},
    "sportswear": {"label": "🏃 Sportswear", "brands": {
        "Nike": "Nike sportswear", "Adidas": "Adidas sportswear", "Puma": "Puma sportswear",
    }},
    "jackets": {"label": "🧥 Jackets", "brands": {
        "Nike": "Nike jacket", "Puma": "Puma jacket", "Woodland": "Woodland jacket",
    }},
    "innerwear": {"label": "🩲 Innerwear", "brands": {
        "Jockey": "Jockey innerwear", "Van Heusen": "Van Heusen innerwear",
    }},
    "sneakers": {"label": "👟 Sneakers", "brands": {
        "Nike": "Nike sneakers", "Adidas": "Adidas sneakers", "Puma": "Puma sneakers",
    }},
    "running_shoes": {"label": "🏃 Running Shoes", "brands": {
        "Nike": "Nike running shoes", "Adidas": "Adidas running shoes", "Asics": "Asics running shoes",
    }},
    "casual_shoes": {"label": "👞 Casual Shoes", "brands": {
        "Woodland": "Woodland casual shoes", "Bata": "Bata casual shoes", "Skechers": "Skechers casual shoes",
    }},
    "formal_shoes": {"label": "👞 Formal Shoes", "brands": {
        "Bata": "Bata formal shoes", "Woodland": "Woodland formal shoes", "Red Tape": "Red Tape formal shoes",
    }},
    "sandals": {"label": "👡 Sandals", "brands": {
        "Bata": "Bata sandals", "Woodland": "Woodland sandals",
    }},
    "slippers": {"label": "🩴 Slippers", "brands": {
        "Bata": "Bata slippers", "Crocs": "Crocs slippers",
    }},
    "bags_backpacks": {"label": "🎒 Bags & Backpacks", "brands": {
        "American Tourister": "American Tourister backpack", "Wildcraft": "Wildcraft backpack", "Skybags": "Skybags backpack",
    }},
}

GROCERY_SUBCATEGORIES = {
    "staples": {"label": "🌾 Staples", "brands": {
        "Rice": "rice", "Atta": "atta flour", "Dal": "dal pulses",
    }},
    "dairy": {"label": "🥛 Dairy", "brands": {
        "Milk": "milk", "Butter": "butter", "Cheese": "cheese",
    }},
    "snacks": {"label": "🍪 Snacks", "brands": {
        "Biscuits": "biscuits", "Chips": "chips", "Namkeen": "namkeen snacks",
    }},
    # ---- NEW grocery subcategories ----
    "fruits_vegetables": {"label": "🥦 Fruits & Vegetables", "brands": {
        "Fruits": "fresh fruits", "Vegetables": "fresh vegetables",
    }},
    "pulses_dal": {"label": "🌾 Pulses & Dal", "brands": {
        "Toor Dal": "toor dal", "Moong Dal": "moong dal", "Chana Dal": "chana dal",
    }},
    "cooking_oil_ghee": {"label": "🛢️ Cooking Oil & Ghee", "brands": {
        "Sunflower Oil": "sunflower cooking oil", "Mustard Oil": "mustard oil", "Ghee": "ghee",
    }},
    "beverages": {"label": "🥤 Beverages", "brands": {
        "Tea": "tea", "Coffee": "coffee", "Juice": "fruit juice",
    }},
    "masalas_spices": {"label": "🌶️ Masalas & Spices", "brands": {
        "Garam Masala": "garam masala", "Turmeric": "turmeric powder", "Chilli Powder": "chilli powder",
    }},
    "instant_packaged_food": {"label": "🍜 Instant & Packaged Food", "brands": {
        "Noodles": "instant noodles", "Pasta": "pasta", "Soup": "instant soup",
    }},
    "personal_care": {"label": "🧴 Personal Care", "brands": {
        "Shampoo": "shampoo", "Soap": "soap", "Toothpaste": "toothpaste",
    }},
    "household_cleaning": {"label": "🧹 Household Cleaning", "brands": {
        "Detergent": "detergent", "Floor Cleaner": "floor cleaner", "Dishwash": "dishwash liquid",
    }},
    "baby_care": {"label": "🍼 Baby Care", "brands": {
        "Diapers": "baby diapers", "Baby Food": "baby food", "Baby Wipes": "baby wipes",
    }},
    "pet_supplies": {"label": "🐾 Pet Supplies", "brands": {
        "Dog Food": "dog food", "Cat Food": "cat food",
    }},
}

BROWSE_GROUPS = {
    "electronics_main": ELECTRONICS_SUBCATEGORIES,
    "electronics_accessories": ACCESSORY_SUBCATEGORIES,
    "clothes": CLOTHES_SUBCATEGORIES,
    "grocery": GROCERY_SUBCATEGORIES,
}

# =============================================================================
# STRICT WEBSITE ROUTING — one explicit section per browse group. Passed
# straight through to scraper.search_products_ranked()/search_products(),
# which (see scraper.py SECTION_SCRAPER_FUNCS) then calls ONLY the scrapers
# assigned to that section — no other site runs in the background.
#   Grocery                    -> JioMart + BigBasket only
#   Electronics / Accessories  -> Amazon + Flipkart + Croma + Reliance Digital only
#   Clothes                    -> Myntra + Flipkart + Amazon only
# A plain typed search (no browse section clicked) has no section context,
# so it keeps the existing keyword-guess behavior in scraper.py — this only
# changes behavior for the browse/category flow, per the request.
# =============================================================================
BROWSE_GROUP_SECTIONS = {
    "electronics_main": "electronics",
    "electronics_accessories": "electronics_accessories",
    "clothes": "fashion",
    "grocery": "grocery",
}


def login_required(f):
    """
    Guards personal-feature routes. Not logged in -> flash a message and
    bounce to /login, remembering where the user was headed (?next=...)
    so they land back there after a successful login (requirement #19).
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login to continue.")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    site_sections = []
    query = ""
    searched = False
    show_categories = False
    show_brands = False

    browse = request.args.get("browse")
    sub_key = request.args.get("sub")
    brand_key = request.args.get("brand")

    subcategory = None
    section = None

    if request.method == "POST":
        query = request.form.get("query", "")
        searched = True

    elif browse and sub_key and brand_key and browse in BROWSE_GROUPS:
        group = BROWSE_GROUPS[browse]
        if sub_key in group and brand_key in group[sub_key]["brands"]:
            query = group[sub_key]["brands"][brand_key]
            searched = True
            # Strict subcategory filtering now applies to every browse group
            # (previously only the 10 Electronics subcategories) — every
            # sub_key here has a matching scraper.py SUBCATEGORY_RULES entry.
            subcategory = sub_key
            # Strict site routing: which section this browse group belongs
            # to, so scraper.py calls ONLY that section's scrapers.
            section = BROWSE_GROUP_SECTIONS.get(browse)

    elif browse and sub_key and browse in BROWSE_GROUPS:
        show_brands = True

    elif browse in BROWSE_GROUPS:
        show_categories = True

    if searched and query:
        try:
            translated_query = GoogleTranslator(source="auto", target="en").translate(query)
        except:
            translated_query = query
        results, site_sections = search_products_ranked(translated_query, subcategory=subcategory, section=section)

        # requirement #15: Recently Compared — only recorded for logged-in
        # users, and only for successful searches with a query.
        if session.get("user_id"):
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO recently_compared (user_id, query) VALUES (?, ?)",
                    (session["user_id"], query),
                )
                db.commit()
                db.close()
            except Exception as e:
                print("recently_compared insert failed:", e)

        # requirement #12: Best Prices Today — snapshot the cheapest REAL
        # result from this search (site-wide, not user-specific) so the
        # homepage can show genuinely-found prices without re-scraping on
        # every page load. Never fabricated: only written when results exist.
        if results:
            try:
                best = results[0]
                db = get_db()
                db.execute(
                    "INSERT INTO trending_prices (query, name, store, price, image, link) VALUES (?, ?, ?, ?, ?, ?)",
                    (query, best["name"], best["site"], best["price"], best.get("image", ""), best.get("link", "")),
                )
                db.commit()
                db.close()
            except Exception as e:
                print("trending_prices insert failed:", e)

    compare_count = 0
    if session.get("user_id"):
        try:
            db = get_db()
            compare_count = db.execute(
                "SELECT COUNT(*) c FROM compare_list WHERE user_id = ?", (session["user_id"],)
            ).fetchone()["c"]
            db.close()
        except Exception as e:
            print("compare_count lookup failed:", e)

    best_prices_today = []
    if not searched and not browse:
        try:
            db = get_db()
            rows = db.execute(
                "SELECT * FROM trending_prices ORDER BY found_at DESC LIMIT 24"
            ).fetchall()
            db.close()
            seen_queries = set()
            for r in rows:
                if r["query"] in seen_queries:
                    continue
                seen_queries.add(r["query"])
                best_prices_today.append(r)
                if len(best_prices_today) >= 6:
                    break
        except Exception as e:
            print("trending_prices lookup failed:", e)

    return render_template(
        "index.html",
        results=results,
        site_sections=site_sections,
        query=query,
        searched=searched,
        show_categories=show_categories,
        show_brands=show_brands,
        browse=browse,
        sub_key=sub_key,
        browse_groups=BROWSE_GROUPS,
        current_user=session.get("user_name"),
        compare_count=compare_count,
        best_prices_today=best_prices_today,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("Please fill in all fields.")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match.")
            return render_template("signup.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            flash("An account with that email already exists.")
            return render_template("signup.html")

        password_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
            (full_name, email, password_hash),
        )
        db.commit()
        new_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        session["user_id"] = new_user["id"]
        session["user_name"] = full_name
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            next_url = request.args.get("next")
            return redirect(next_url if next_url else url_for("home"))

        flash("Invalid email or password.")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/profile")
@login_required
def profile():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    collections_count = db.execute(
        "SELECT COUNT(*) c FROM collections WHERE user_id = ?", (session["user_id"],)
    ).fetchone()["c"]
    compare_count = db.execute(
        "SELECT COUNT(*) c FROM compare_list WHERE user_id = ?", (session["user_id"],)
    ).fetchone()["c"]
    saved_count = db.execute(
        "SELECT COUNT(*) c FROM saved_products WHERE user_id = ?", (session["user_id"],)
    ).fetchone()["c"]
    recent = db.execute(
        "SELECT query, MAX(searched_at) AS searched_at FROM recently_compared WHERE user_id = ? GROUP BY query ORDER BY searched_at DESC LIMIT 5",
        (session["user_id"],),
    ).fetchall()
    db.close()

    return render_template(
        "profile.html",
        user=user,
        collections_count=collections_count,
        compare_count=compare_count,
        saved_count=saved_count,
        recent=recent,
    )



# ---------------------------------------------------------------------------
# Phase 4 — Compare List & Collections. All routes below require login
# (login_required). Every query filters by session["user_id"] so a user
# can never read/modify another user's compare list or collections.
# ---------------------------------------------------------------------------

@app.route("/compare")
@login_required
def compare():
    db = get_db()
    items = db.execute(
        "SELECT * FROM compare_list WHERE user_id = ? ORDER BY added_at DESC",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("compare.html", items=items)


@app.route("/compare/add", methods=["POST"])
@login_required
def compare_add():
    name = request.form.get("name", "")
    store = request.form.get("store", "")
    price = request.form.get("price", "")
    image = request.form.get("image", "")
    link = request.form.get("link", "")

    db = get_db()
    db.execute(
        "INSERT INTO compare_list (user_id, name, store, price, image, link) VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], name, store, price, image, link),
    )
    db.commit()
    db.close()
    flash(f'Added "{name}" to your Compare List.')
    return redirect(request.referrer or url_for("home"))


@app.route("/compare/remove/<int:item_id>", methods=["POST"])
@login_required
def compare_remove(item_id):
    db = get_db()
    db.execute(
        "DELETE FROM compare_list WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"]),
    )
    db.commit()
    db.close()
    return redirect(url_for("compare"))


@app.route("/compare/clear", methods=["POST"])
@login_required
def compare_clear():
    db = get_db()
    db.execute("DELETE FROM compare_list WHERE user_id = ?", (session["user_id"],))
    db.commit()
    db.close()
    return redirect(url_for("compare"))


@app.route("/collections")
@login_required
def collections():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM collections WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],),
    ).fetchall()

    collections_list = []
    for c in rows:
        count = db.execute(
            "SELECT COUNT(*) c FROM collection_products WHERE collection_id = ?", (c["id"],)
        ).fetchone()["c"]
        collections_list.append({"id": c["id"], "name": c["name"], "count": count})
    db.close()

    # If arriving from a product's "Save" button, these query params carry
    # the product so it can be added right after picking/creating a collection.
    pending_product = None
    if request.args.get("save_name"):
        pending_product = {
            "name": request.args.get("save_name", ""),
            "store": request.args.get("save_store", ""),
            "price": request.args.get("save_price", ""),
            "image": request.args.get("save_image", ""),
            "link": request.args.get("save_link", ""),
        }

    return render_template("collections.html", collections=collections_list, pending_product=pending_product)


@app.route("/collections/create", methods=["POST"])
@login_required
def collections_create():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Collection name can't be empty.")
        return redirect(url_for("collections"))

    db = get_db()
    db.execute("INSERT INTO collections (user_id, name) VALUES (?, ?)", (session["user_id"], name))
    db.commit()
    new_col = db.execute(
        "SELECT id FROM collections WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (session["user_id"],),
    ).fetchone()

    # If a product was pending (came from a Save action), add it immediately.
    if request.form.get("save_name"):
        db.execute(
            "INSERT INTO collection_products (collection_id, name, store, price, image, link) VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_col["id"],
                request.form.get("save_name", ""),
                request.form.get("save_store", ""),
                request.form.get("save_price", ""),
                request.form.get("save_image", ""),
                request.form.get("save_link", ""),
            ),
        )
        db.commit()

    db.close()
    return redirect(url_for("collection_detail", collection_id=new_col["id"]))


@app.route("/collections/<int:collection_id>")
@login_required
def collection_detail(collection_id):
    db = get_db()
    col = db.execute(
        "SELECT * FROM collections WHERE id = ? AND user_id = ?",
        (collection_id, session["user_id"]),
    ).fetchone()
    if not col:
        db.close()
        flash("Collection not found.")
        return redirect(url_for("collections"))

    products = db.execute(
        "SELECT * FROM collection_products WHERE collection_id = ? ORDER BY added_at DESC",
        (collection_id,),
    ).fetchall()
    db.close()
    return render_template("collection_detail.html", collection=col, products=products)


@app.route("/collections/<int:collection_id>/add", methods=["POST"])
@login_required
def collections_add_product(collection_id):
    db = get_db()
    col = db.execute(
        "SELECT id FROM collections WHERE id = ? AND user_id = ?",
        (collection_id, session["user_id"]),
    ).fetchone()
    if not col:
        db.close()
        flash("Collection not found.")
        return redirect(url_for("collections"))

    db.execute(
        "INSERT INTO collection_products (collection_id, name, store, price, image, link) VALUES (?, ?, ?, ?, ?, ?)",
        (
            collection_id,
            request.form.get("name", ""),
            request.form.get("store", ""),
            request.form.get("price", ""),
            request.form.get("image", ""),
            request.form.get("link", ""),
        ),
    )
    db.commit()
    db.close()
    flash("Added to collection.")
    return redirect(url_for("collection_detail", collection_id=collection_id))


@app.route("/collections/<int:collection_id>/rename", methods=["POST"])
@login_required
def collections_rename(collection_id):
    new_name = request.form.get("name", "").strip()
    db = get_db()
    if new_name:
        db.execute(
            "UPDATE collections SET name = ? WHERE id = ? AND user_id = ?",
            (new_name, collection_id, session["user_id"]),
        )
        db.commit()
    db.close()
    return redirect(url_for("collection_detail", collection_id=collection_id))


@app.route("/collections/<int:collection_id>/delete", methods=["POST"])
@login_required
def collections_delete(collection_id):
    db = get_db()
    db.execute(
        "DELETE FROM collections WHERE id = ? AND user_id = ?",
        (collection_id, session["user_id"]),
    )
    db.commit()
    db.close()
    return redirect(url_for("collections"))


@app.route("/collections/<int:collection_id>/remove/<int:product_id>", methods=["POST"])
@login_required
def collections_remove_product(collection_id, product_id):
    db = get_db()
    owns = db.execute(
        """SELECT cp.id FROM collection_products cp
           JOIN collections c ON cp.collection_id = c.id
           WHERE cp.id = ? AND c.id = ? AND c.user_id = ?""",
        (product_id, collection_id, session["user_id"]),
    ).fetchone()
    if owns:
        db.execute("DELETE FROM collection_products WHERE id = ?", (product_id,))
        db.commit()
    db.close()
    return redirect(url_for("collection_detail", collection_id=collection_id))



# ---------------------------------------------------------------------------
# Phase 5 — Saved Products: a flat "favorites" list, separate from
# Collections. No collection picker needed — one tap saves it here.
# Every query filters by session["user_id"].
# ---------------------------------------------------------------------------

@app.route("/saved")
@login_required
def saved_products():
    db = get_db()
    items = db.execute(
        "SELECT * FROM saved_products WHERE user_id = ? ORDER BY saved_at DESC",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("saved.html", items=items)


@app.route("/saved/add", methods=["POST"])
@login_required
def saved_add():
    name = request.form.get("name", "")
    store = request.form.get("store", "")
    price = request.form.get("price", "")
    image = request.form.get("image", "")
    link = request.form.get("link", "")

    db = get_db()
    db.execute(
        "INSERT INTO saved_products (user_id, name, store, price, image, link) VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], name, store, price, image, link),
    )
    db.commit()
    db.close()
    flash(f'Saved "{name}".')
    return redirect(request.referrer or url_for("home"))


@app.route("/saved/remove/<int:item_id>", methods=["POST"])
@login_required
def saved_remove(item_id):
    db = get_db()
    db.execute(
        "DELETE FROM saved_products WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"]),
    )
    db.commit()
    db.close()
    return redirect(url_for("saved_products"))



def extract_query_from_url(url):
    """
    Heuristic, honest product-name extraction from a pasted URL — no
    external API, no guaranteed accuracy. Looks at the URL path for the
    slug segment that looks most like a product title (multiple hyphens/
    underscores), strips common non-title tokens (dp, itm, p, product),
    and title-cases the result. Returns None if nothing usable is found,
    so the route can tell the user honestly instead of guessing.
    """
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        segments = [s for s in path.split('/') if s]
        if not segments:
            return None

        candidates = [s for s in segments if s.count('-') >= 2 or s.count('_') >= 2]
        target = max(candidates, key=len) if candidates else max(segments, key=len)

        target = re.sub(r'\.(html?|php|aspx)$', '', target, flags=re.I)
        cleaned = re.sub(r'[-_]+', ' ', target).strip()
        cleaned = re.sub(r'\b(dp|itm|p|pid|product|products|item)\b', '', cleaned, flags=re.I)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # reject results that are mostly digits/ids (not a real product name)
        letters = sum(c.isalpha() for c in cleaned)
        if len(cleaned) < 3 or letters < 3:
            return None

        return cleaned.title()
    except Exception:
        return None


@app.route("/analyze", methods=["GET", "POST"])
def analyze():
    submitted_url = ""
    extracted_query = None
    results = []
    analyzed = False
    error = None

    if request.method == "POST":
        submitted_url = request.form.get("product_url", "").strip()
        analyzed = True

        if not submitted_url.lower().startswith("http"):
            error = "That doesn't look like a valid URL — please paste a full product link (starting with http:// or https://)."
        else:
            extracted_query = extract_query_from_url(submitted_url)
            if not extracted_query:
                error = "Couldn't identify a product name from this URL. Try a direct product page link, or search by name on the homepage instead."
            else:
                try:
                    translated_query = GoogleTranslator(source="auto", target="en").translate(extracted_query)
                except:
                    translated_query = extracted_query
                results = search_products(translated_query)[:10]
                if not results:
                    error = f'RKart checked all 6 stores for "{extracted_query}" but found no matches. The product name guessed from your URL may not be accurate.'

    return render_template(
        "analyze.html",
        submitted_url=submitted_url,
        extracted_query=extracted_query,
        results=results,
        analyzed=analyzed,
        error=error,
        current_user=session.get("user_name"),
    )


if __name__ == "__main__":
    app.run(debug=False)