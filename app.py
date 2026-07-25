from flask import Flask, render_template, request
from scraper import search_products
from deep_translator import GoogleTranslator

app = Flask(__name__)

CATEGORY_QUERIES = {
    "clothes": "shirts for men",
    "grocery": "rice 5kg",
    "electronics": "bluetooth earphones",
}


@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    query = ""
    searched = False

    if request.method == "POST":
        query = request.form.get("query", "")
        searched = True
    elif request.args.get("category"):
        query = CATEGORY_QUERIES.get(request.args.get("category"), "")
        searched = True

    if searched and query:
        try:
            translated_query = GoogleTranslator(source="auto", target="en").translate(query)
        except:
            translated_query = query
        results = search_products(translated_query)[:5]

    return render_template("index.html", results=results, query=query, searched=searched)


if __name__ == "__main__":
    app.run(debug=False)from flask import Flask, render_template, request
from scraper import search_products
from deep_translator import GoogleTranslator

app = Flask(__name__)

CATEGORY_QUERIES = {
    "clothes": "shirts for men",
    "grocery": "rice 5kg",
    "electronics": "bluetooth earphones",
}


@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    query = ""
    searched = False

    if request.method == "POST":
        query = request.form.get("query", "")
        searched = True
    elif request.args.get("category"):
        query = CATEGORY_QUERIES.get(request.args.get("category"), "")
        searched = True

    if searched and query:
        try:
            translated_query = GoogleTranslator(source="auto", target="en").translate(query)
        except:
            translated_query = query
        results = search_products(translated_query)[:5]

    return render_template("index.html", results=results, query=query, searched=searched)


if __name__ == "__main__":
    app.run(debug=False)