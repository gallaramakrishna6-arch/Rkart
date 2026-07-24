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


def scroll_full_page(driver):
    # పేజీ కిందకి నెమ్మదిగా స్క్రోల్ చేయడం, అన్ని ఇమేజెస్/products లోడ్ అవ్వడానికి
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(6):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollTo(0, 0);")  # పైకి తిరిగి రావడం
    time.sleep(1)


def search_flipkart(query):
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.get(f"https://www.flipkart.com/search?q={query.replace(' ', '+')}")
    time.sleep(3)

    try:
        driver.find_element(By.XPATH, "//button[text()='✕']").click()
    except:
        pass
    time.sleep(1)

    # ముఖ్యమైన కొత్త స్టెప్ — స్క్రోల్ చేసి అన్ని ఇమేజెస్ లోడ్ చేయడం
    scroll_full_page(driver)

    results = []
    price_elements = driver.find_elements(By.XPATH, "//div[starts-with(text(), '₹')]")

    for price_el in price_elements:
        price_text = price_el.text.strip()
        price = clean_price(price_text)
        if not price:
            continue

        name = find_best_name(price_el)
        results.append({"site": "Flipkart", "name": name, "price": price})

    driver.quit()

    seen = set()
    unique_results = []
    for item in results:
        key = (item["name"], item["price"])
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    return unique_results


if __name__ == "__main__":
    query = input("ఏం సెర్చ్ చేయాలి? (ఉదా: nike shoes): ")
    data = search_flipkart(query)

    print(f"\n{len(data)} products dorikayi!\n")
    data.sort(key=lambda x: x["price"])
    for item in data[:10]:
        print(f"₹{item['price']:.2f}  -  {item['name']}")