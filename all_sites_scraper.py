from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import re


def get_driver():
    options = Options()
    options.add_argument("--start-maximized")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


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


# ---------------- AMAZON ----------------
def search_amazon(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.amazon.in/s?k={query.replace(' ', '+')}")
        time.sleep(3)

        products = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
        for product in products:
            try:
                name = product.find_element(By.CSS_SELECTOR, "h2 span").text.strip()
                price_whole = product.find_element(By.CSS_SELECTOR, "span.a-price-whole").text.strip()
                price = clean_price(price_whole)
                if name and price:
                    results.append({"site": "Amazon", "name": name, "price": price})
            except:
                continue
    except Exception as e:
        print("Amazon error:", e)
    driver.quit()
    return results


# ---------------- FLIPKART ----------------
def is_junk_line(line):
    line = line.strip()
    if not line:
        return True
    if line.startswith("₹"):
        return True
    if "% off" in line.lower():
        return True
    if re.fullmatch(r"[\d,.]+", line):
        return True
    if line.lower() in ("only few left", "add to compare", "sponsored"):
        return True
    return False


def find_best_name(price_el):
    best_name = "Unknown"
    best_len = 0
    for level in range(2, 7):
        try:
            container = price_el.find_element(By.XPATH, f"./ancestor::div[{level}]")
            lines = container.text.strip().split("\n")
            for line in lines:
                if is_junk_line(line):
                    continue
                if len(line) > best_len:
                    best_len = len(line)
                    best_name = line.strip()
        except:
            continue
    return best_name


def search_flipkart(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.flipkart.com/search?q={query.replace(' ', '+')}")
        time.sleep(3)
        try:
            driver.find_element(By.XPATH, "//button[text()='✕']").click()
        except:
            pass
        time.sleep(1)

        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, "//div[starts-with(text(), '₹')]")
        seen = set()
        for price_el in price_elements:
            price_text = price_el.text.strip()
            price = clean_price(price_text)
            if not price:
                continue
            name = find_best_name(price_el)
            key = (name, price)
            if key not in seen:
                seen.add(key)
                results.append({"site": "Flipkart", "name": name, "price": price})
    except Exception as e:
        print("Flipkart error:", e)
    driver.quit()
    return results


# ---------------- MYNTRA ----------------
def search_myntra(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.myntra.com/{query.replace(' ', '-')}")
        time.sleep(3)
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
            if name and price:
                results.append({"site": "Myntra", "name": name, "price": price})
    except Exception as e:
        print("Myntra error:", e)
    driver.quit()
    return results


# ---------------- MAIN ----------------
if __name__ == "__main__":
    query = input("ఏం సెర్చ్ చేయాలి? (ఉదా: nike shoes): ")

    all_results = []
    print("\nAmazon చెక్ చేస్తోంది...")
    all_results += search_amazon(query)

    print("Flipkart చెక్ చేస్తోంది...")
    all_results += search_flipkart(query)

    print("Myntra చెక్ చేస్తోంది...")
    all_results += search_myntra(query)

    print(f"\n✅ మొత్తం {len(all_results)} products దొరికాయి\n")

    if all_results:
        all_results.sort(key=lambda x: x["price"])
        print("Cheapest ఫలితాలు (అన్ని సైట్‌లు కలిపి):")
        print("-" * 50)
        for item in all_results[:10]:
            print(f"₹{item['price']:.2f}  [{item['site']}]  -  {item['name']}")

        best = all_results[0]
        print(f"\n🏆 CHEAPEST: {best['name']} — ₹{best['price']:.2f} ({best['site']})")