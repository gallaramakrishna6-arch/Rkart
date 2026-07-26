import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import re


def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1024,768")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def clean_price(price_text):
    match = re.search(r"[\d,]+", price_text.replace(",", ""))
    return float(match.group().replace(",", "")) if match else None


def scroll_full_page(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.7)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)


DEFAULT_IMAGE = "https://placehold.co/150x150?text=No+Image"


def get_image_src(img_element):
    for attr in ["src", "data-src", "data-image-source", "srcset"]:
        value = img_element.get_attribute(attr)
        if value and value.startswith("http"):
            return value.split(" ")[0]
    return DEFAULT_IMAGE


def search_amazon(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.amazon.in/s?k={query.replace(' ', '+')}")
        time.sleep(2.5)

        products = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
        for product in products:
            try:
                name = product.find_element(By.CSS_SELECTOR, "h2 span").text.strip()
                price_whole = product.find_element(By.CSS_SELECTOR, "span.a-price-whole").text.strip()
                price = clean_price(price_whole)

                try:
                    link = product.find_element(By.XPATH, ".//a[contains(@href, '/dp/')]").get_attribute("href")
                except:
                    try:
                        link = product.find_element(By.CSS_SELECTOR, "a.a-link-normal").get_attribute("href")
                    except:
                        link = "https://www.amazon.in/s?k=" + query.replace(" ", "+")

                try:
                    img = product.find_element(By.CSS_SELECTOR, "img.s-image")
                    image = get_image_src(img)
                except:
                    image = DEFAULT_IMAGE

                if name and price:
                    results.append({"site": "Amazon", "name": name, "price": price, "link": link, "image": image})
            except:
                continue
    except Exception as e:
        print("Amazon error:", e)
    driver.quit()
    return results


def is_junk_line(line):
    line = line.strip()
    if not line or line.startswith("₹") or "% off" in line.lower():
        return True
    if re.fullmatch(r"[\d,.]+", line):
        return True
    if line.lower() in ("only few left", "add to compare", "sponsored", "buy now", "out of stock", "login"):
        return True
    if "!" in line or line.count(".") > 1:
        return True
    if any(word in line.lower() for word in [" i ", "recommend", "review", "excellent", "worst", "good product", "bad product", "using this", "emi", "left"]):
        return True
    word_count = len(line.split())
    if word_count > 10 or word_count == 0:
        return True
    return False


def get_card_container(price_el):
    # ముందుగా, ఈ price ఏ <a> లింక్ లోపల ఉందో చూడటం — ఇదే సాధారణంగా పూర్తి ప్రొడక్ట్ కార్డ్
    try:
        anchors = price_el.find_elements(By.XPATH, "./ancestor::a")
        if anchors:
            return anchors[-1]
    except:
        pass
    # <a> దొరకకపోతే, ఒక స్థిరమైన div స్థాయి వాడటం
    for level in [4, 3, 5, 2, 6]:
        try:
            return price_el.find_element(By.XPATH, f"./ancestor::div[{level}]")
        except:
            continue
    return None


def extract_name_from_container(container):
    best_name = "Unknown"
    best_len = 0
    try:
        for line in container.text.strip().split("\n"):
            if not is_junk_line(line) and len(line) > best_len:
                best_len = len(line)
                best_name = line.strip()
    except:
        pass
    return best_name


def extract_image_from_container(container, fallback_link):
    image = DEFAULT_IMAGE
    link = fallback_link
    try:
        img = container.find_element(By.TAG_NAME, "img")
        image = get_image_src(img)
    except:
        pass
    try:
        href = container.get_attribute("href")
        if href:
            link = href
    except:
        pass
    return image, link


def search_flipkart(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.flipkart.com/search?q={query.replace(' ', '+')}")
        time.sleep(2)
        try:
            driver.find_element(By.XPATH, "//button[text()='✕']").click()
        except:
            pass
        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, "//div[starts-with(text(), '₹')]")
        seen = set()
        fallback = "https://www.flipkart.com/search?q=" + query.replace(" ", "+")
        for price_el in price_elements:
            price = clean_price(price_el.text.strip())
            if not price:
                continue

            container = get_card_container(price_el)
            if container is None:
                continue

            name = extract_name_from_container(container)
            image, link = extract_image_from_container(container, fallback)

            key = (name, price)
            if key not in seen and name != "Unknown":
                seen.add(key)
                results.append({"site": "Flipkart", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("Flipkart error:", e)
    driver.quit()
    return results


def search_myntra(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.myntra.com/{query.replace(' ', '-')}")
        time.sleep(2)
        scroll_full_page(driver)

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
                try:
                    price_text = product.find_element(By.CSS_SELECTOR, ".product-price span").text.strip()
                except:
                    continue
            price = clean_price(price_text)
            name = f"{brand} {title}".strip()

            try:
                img = product.find_element(By.TAG_NAME, "img")
                image = get_image_src(img)
            except:
                image = DEFAULT_IMAGE

            try:
                link = product.find_element(By.TAG_NAME, "a").get_attribute("href")
            except:
                link = "https://www.myntra.com/" + query.replace(" ", "-")

            if name and price:
                results.append({"site": "Myntra", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("Myntra error:", e)
    driver.quit()
    return results


def search_bigbasket(query):
    driver = get_driver()
    results = []
    try:
        url = f"https://www.bigbasket.com/ps/?q={query.replace(' ', '+')}"
        driver.get(url)
        time.sleep(2.5)
        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, "//span[starts-with(text(), '₹')]")
        seen = set()
        for price_el in price_elements:
            price = clean_price(price_el.text.strip())
            if not price:
                continue
            container = get_card_container(price_el)
            if container is None:
                continue
            name = extract_name_from_container(container)
            image, link = extract_image_from_container(container, url)
            key = (name, price)
            if key not in seen and name != "Unknown":
                seen.add(key)
                results.append({"site": "BigBasket", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("BigBasket error:", e)
    driver.quit()
    return results


def search_zepto(query):
    driver = get_driver()
    results = []
    try:
        url = f"https://www.zeptonow.com/search?query={query.replace(' ', '%20')}"
        driver.get(url)
        time.sleep(2.5)
        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, "//*[starts-with(text(), '₹')]")
        seen = set()
        for price_el in price_elements:
            price = clean_price(price_el.text.strip())
            if not price:
                continue
            container = get_card_container(price_el)
            if container is None:
                continue
            name = extract_name_from_container(container)
            image, link = extract_image_from_container(container, url)
            key = (name, price)
            if key not in seen and name != "Unknown":
                seen.add(key)
                results.append({"site": "Zepto", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("Zepto error:", e)
    driver.quit()
    return results


def search_blinkit(query):
    driver = get_driver()
    results = []
    try:
        url = f"https://blinkit.com/s/?q={query.replace(' ', '%20')}"
        driver.get(url)
        time.sleep(2.5)
        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, "//*[starts-with(text(), '₹')]")
        seen = set()
        for price_el in price_elements:
            price = clean_price(price_el.text.strip())
            if not price:
                continue
            container = get_card_container(price_el)
            if container is None:
                continue
            name = extract_name_from_container(container)
            image, link = extract_image_from_container(container, url)
            key = (name, price)
            if key not in seen and name != "Unknown":
                seen.add(key)
                results.append({"site": "Blinkit", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("Blinkit error:", e)
    driver.quit()
    return results


GROCERY_KEYWORDS = [
    "milk", "rice", "atta", "flour", "oil", "sugar", "salt", "maggi", "noodles",
    "biscuit", "snacks", "tea", "coffee", "soap", "shampoo", "vegetable", "fruit",
    "grocery", "dal", "pulses", "ghee", "butter", "bread", "egg", "paneer",
    "detergent", "cleaner", "toothpaste", "juice", "water", "chips"
]


def search_products(query):
    query_lower = query.lower()
    is_grocery = any(word in query_lower for word in GROCERY_KEYWORDS)

    all_results = []
    if is_grocery:
        all_results += search_zepto(query)
        all_results += search_blinkit(query)
    else:
        all_results += search_amazon(query)
        all_results += search_flipkart(query)

    query_words = [w.lower() for w in query.split() if len(w) > 2]
    filtered_results = []
    for item in all_results:
        item_name_lower = item["name"].lower()
        if any(word in item_name_lower for word in query_words):
            filtered_results.append(item)

    filtered_results.sort(key=lambda x: x["price"])
    return filtered_results[:5]
