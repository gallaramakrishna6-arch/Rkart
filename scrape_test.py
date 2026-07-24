import re
import time
import requests
from bs4 import BeautifulSoup

def scrape_all_pages():
    base_url = "https://books.toscrape.com/catalogue/page-{}.html"
    all_results = []
    page = 1

    while True:
        url = base_url.format(page)
        response = requests.get(url)
        response.encoding = "utf-8"

        if response.status_code != 200:
            print(f"Page {page} దొరకలేదు — స్క్రాపింగ్ పూర్తయ్యింది.")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        books = soup.find_all("article", class_="product_pod")

        if not books:
            break

        for book in books:
            title = book.h3.a["title"]
            price_text = book.find("p", class_="price_color").text
            match = re.search(r"[\d.]+", price_text)
            if not match:
                continue
            price = float(match.group())

            all_results.append({"name": title, "price": price})

        print(f"Page {page} scrape ayyindi — {len(books)} products dorikayi")
        page += 1
        time.sleep(0.3)

    return all_results


if __name__ == "__main__":
    data = scrape_all_pages()

    print(f"\n✅ Total {len(data)} products dorikayi!\n")

    cheapest = sorted(data, key=lambda x: x["price"])[:5]

    print("Cheapest 5 products (out of all pages):")
    print("-" * 50)
    for item in cheapest:
        print(f"₹{item['price']:.2f}  -  {item['name']}")