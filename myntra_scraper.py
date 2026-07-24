from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import re


def clean_price(price_text):
    match = re.search(r"[\d,]+", price_text.replace(",", ""))
    return float(match.group().replace(",", "")) if match else None


def scroll_full_page(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(6):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)


def search_myntra(query):
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.get(f"https://www.myntra.com/{query.replace(' ', '-')}")
    time.sleep(3)

    scroll_full_page(driver)

    results = []

    # ప్రతి ప్రొడక్ట్ ఒక <li class="product-base"> లో ఉంటుంది
    products = driver.find_elements(By.CSS_SELECTOR, "li.product-base")

    for product in products:
        try:
            brand = product.find_element(By.CSS_SELECTOR, ".product-brand").text.strip()
        except:
            brand = ""

        try:
            title = product.find_element(By.CSS_SELECTOR, ".product-product").text.strip()
        except:
            title = ""

        try:
            price_text = product.find_element(By.CSS_SELECTOR, ".product-discountedPrice").text.strip()
        except:
            # discount లేని ప్రొడక్ట్స్ కి వేరే class ఉండచ్చు
            try:
                price_text = product.find_element(By.CSS_SELECTOR, ".product-price span").text.strip()
            except:
                continue

        price = clean_price(price_text)
        name = f"{brand} {title}".strip()

        if name and price:
            results.append({"site": "Myntra", "name": name, "price": price})

    driver.quit()
    return results


if __name__ == "__main__":
    query = input("ఏం సెర్చ్ చేయాలి? (ఉదా: nike shoes): ")
    data = search_myntra(query)

    print(f"\n{len(data)} products dorikayi!\n")
    data.sort(key=lambda x: x["price"])
    for item in data[:10]:
        print(f"₹{item['price']:.2f}  -  {item['name']}")