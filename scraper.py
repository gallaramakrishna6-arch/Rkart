import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, InvalidSessionIdException
import time
import re
import difflib
import concurrent.futures

# Railway (and most PaaS free/hobby tiers) give this app far less RAM than
# a local dev machine, and 4 simultaneous headless Chrome instances is what
# was crashing the deployed worker (gunicorn logs showed repeated WORKER
# TIMEOUT -> SIGKILL). RAILWAY_ENVIRONMENT is set automatically by Railway;
# PORT is also always set in that kind of hosted environment and not
# typically set when running `python app.py` locally, so either check
# reliably tells us "this is NOT the local dev machine".
IS_PRODUCTION = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("PORT"))


SITE_LOGOS = {
    "Amazon": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg",
    "Flipkart": "https://upload.wikimedia.org/wikipedia/commons/7/7a/Flipkart_logo.svg",
    "Croma": "https://www.croma.com/favicon.ico",
    "Reliance Digital": "https://www.reliancedigital.in/favicon.ico",
    "Myntra": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Myntra_logo.png",
    "JioMart": "https://www.jiomart.com/favicon.ico",
    "BigBasket": "https://www.bigbasket.com/favicon.ico",
}

ACTIVE_STORES = ["Amazon", "Flipkart", "Croma", "Reliance Digital", "Myntra", "JioMart", "BigBasket"]


def get_driver(proxy=None):
    import tempfile
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1024,768")
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='chrome_profile_')}")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def safe_quit(driver):
    try:
        driver.quit()
    except Exception:
        pass


def clean_price(price_text):
    match = re.search(r"[\d,]+", price_text.replace(",", ""))
    return float(match.group().replace(",", "")) if match else None


def scroll_full_page(driver, passes=3):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(passes):
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
    for attr in ["src", "data-src", "data-image-source", "data-original",
                 "data-lazy", "data-lazy-src", "srcset"]:
        try:
            value = img_element.get_attribute(attr)
        except Exception:
            continue
        if value and value.startswith("http"):
            return value.split(" ")[0]
    return DEFAULT_IMAGE


def is_junk_line(line):
    line = line.strip()
    if not line or line.startswith("₹") or "% off" in line.lower():
        return True
    if re.fullmatch(r"[\d,.]+", line):
        return True
    if line.lower() in ("only few left", "add to compare", "sponsored", "buy now", "out of stock", "login", "add"):
        return True
    if "!" in line or line.count(".") > 1:
        return True
    if any(word in line.lower() for word in [" i ", "recommend", "review", "excellent", "worst", "good product", "bad product", "using this", "emi", "left", "protect promise"]):
        return True
    if "|" in line:
        return True
    word_count = len(line.split())
    if ":" in line and word_count <= 5:
        return True
    if word_count > 10 or word_count <= 1:
        return True
    return False


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
            return image, href
    except:
        pass

    try:
        a = container.find_element(By.TAG_NAME, "a")
        href = a.get_attribute("href")
        if href:
            return image, href
    except:
        pass

    try:
        a = container.find_element(By.XPATH, "./ancestor::a[1]")
        href = a.get_attribute("href")
        if href:
            link = href
    except:
        pass

    return image, link


def get_card_container(price_el):
    for level in [4, 3, 5, 2, 6]:
        try:
            return price_el.find_element(By.XPATH, f"./ancestor::div[{level}]")
        except:
            continue
    return None


def generic_price_scan(driver, url, site_name, price_tag="div"):
    results = []
    try:
        driver.get(url)
        time.sleep(2.5)
        scroll_full_page(driver)

        price_elements = driver.find_elements(By.XPATH, f"//{price_tag}[starts-with(text(), '₹')] | //span[starts-with(text(), '₹')]")
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
                results.append({"site": site_name, "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print(f"{site_name} error:", e)
    return results


def search_amazon(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.amazon.in/s?k={query.replace(' ', '+')}")
        time.sleep(2.5)

        products = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
        for product in products:
            try:
                name = ""
                try:
                    img_alt = product.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("alt")
                    name = (img_alt or "").strip()
                except:
                    pass

                if not name:
                    try:
                        name = product.find_element(By.CSS_SELECTOR, "h2").text.strip()
                    except:
                        pass

                if not name:
                    try:
                        link_el = product.find_element(By.XPATH, ".//a[contains(@href, '/dp/')]")
                        name = (link_el.get_attribute("aria-label") or link_el.text or "").strip()
                    except:
                        pass

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
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
                    time.sleep(0.2)
                    image = get_image_src(img)
                except:
                    image = DEFAULT_IMAGE

                if name and price:
                    results.append({"site": "Amazon", "name": name, "price": price, "link": link, "image": image})
            except:
                continue
    except Exception as e:
        print("Amazon error:", e)
    safe_quit(driver)
    return results


def search_flipkart(query):
    driver = get_driver()
    results = []
    try:
        driver.get(f"https://www.flipkart.com/search?q={query.replace(' ', '%20')}")
        time.sleep(2.5)

        try:
            close_btn = driver.find_element(By.XPATH, "//button[contains(text(),'✕')]")
            close_btn.click()
            time.sleep(0.4)
        except:
            pass

        scroll_full_page(driver)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/itm']")
        print(f"Flipkart: found {len(anchors)} product links for '{query}'")

        BAD_NAME_MARKERS = ("add to compare", "ratings", "reviews", "% off", "sponsored")

        def looks_like_junk(line):
            low = line.lower()
            return any(marker in low for marker in BAD_NAME_MARKERS) or is_junk_line(line)

        def best_image_alt(container):
            try:
                imgs = container.find_elements(By.TAG_NAME, "img")
            except:
                return ""
            best = ""
            for img in imgs:
                try:
                    alt = (img.get_attribute("alt") or "").strip()
                except:
                    continue
                if len(alt.split()) >= 3 and len(alt) > len(best):
                    best = alt
            return best

        def distinct_product_count(container):
            try:
                hrefs = set()
                for el in container.find_elements(By.CSS_SELECTOR, "a[href*='/p/itm']"):
                    h = el.get_attribute("href") or ""
                    h = h.split("?")[0].split("#")[0]
                    if h:
                        hrefs.add(h)
                return len(hrefs) if hrefs else 1
            except:
                return 1

        seen_norm = set()
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if not href:
                    continue
                link = href if href.startswith("http") else "https://www.flipkart.com" + href

                name = (a.get_attribute("title") or "").strip()
                has_own_image = False
                if not name:
                    try:
                        alt_img = a.find_element(By.TAG_NAME, "img")
                        has_own_image = True
                        name = (alt_img.get_attribute("alt") or "").strip()
                    except:
                        pass
                else:
                    try:
                        a.find_element(By.TAG_NAME, "img")
                        has_own_image = True
                    except:
                        pass

                if not name and not has_own_image:
                    continue

                price = None
                image = DEFAULT_IMAGE

                card = a
                for _ in range(8):
                    try:
                        candidate = card.find_element(By.XPATH, "..")
                    except:
                        break

                    if distinct_product_count(candidate) > 1:
                        break

                    card = candidate

                    if not name:
                        img_alt_name = best_image_alt(card)
                        if img_alt_name:
                            name = img_alt_name

                    if not name:
                        try:
                            best_line = ""
                            for line in card.text.strip().split("\n"):
                                line = line.strip()
                                if line and not looks_like_junk(line) and len(line) > len(best_line):
                                    best_line = line
                            if best_line:
                                name = best_line
                        except:
                            pass

                    if price is None:
                        try:
                            price_el = card.find_element(
                                By.XPATH,
                                ".//div[contains(normalize-space(text()), '₹')] | "
                                ".//span[contains(normalize-space(text()), '₹')]"
                            )
                            price_text = price_el.get_attribute("textContent").strip().split("\n")[0]
                            price = clean_price(price_text)
                        except:
                            pass

                    if image == DEFAULT_IMAGE:
                        try:
                            img = card.find_element(By.TAG_NAME, "img")
                            image = get_image_src(img)
                        except:
                            pass

                    if name and price:
                        break

                SPEC_CHIP_PATTERNS = (
                    r"\bprocessor(\s*\(.*\))?$",
                    r"operating system$",
                    r"^for\s+\w",
                    r"^\d+\s*(gb|tb)\b",
                )
                name_lower_check = name.lower().strip()
                if any(re.search(pat, name_lower_check) for pat in SPEC_CHIP_PATTERNS):
                    continue

                if not name or not price or looks_like_junk(name):
                    continue

                norm_key = (re.sub(r"\s+", " ", name.lower()).strip(), price)
                if norm_key in seen_norm:
                    continue
                seen_norm.add(norm_key)

                results.append({"site": "Flipkart", "name": name, "price": price, "link": link, "image": image})
            except:
                continue
    except Exception as e:
        print("Flipkart error:", e)

    safe_quit(driver)
    print(f"Flipkart: returning {len(results)} products for '{query}'")
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
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
                time.sleep(0.2)
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
    safe_quit(driver)
    return results


def search_croma(query):
    driver = get_driver()
    results = []
    had_name = 0
    had_price = 0
    try:
        q_enc = query.replace(' ', '%20')
        url = f"https://www.croma.com/searchB?q={q_enc}%3Arelevance&text={q_enc}"
        driver.get(url)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-info, a[href*='/p/']"))
            )
        except Exception:
            print(f"Croma DEBUG: nothing appeared for '{query}'. "
                  f"page_source length = {len(driver.page_source)}")

        scroll_full_page(driver, passes=4)

        seen = set()

        info_blocks = driver.find_elements(By.CSS_SELECTOR, "div.product-info")
        print(f"Croma: found {len(info_blocks)} product-info blocks for '{query}'")

        for info in info_blocks:
            try:
                a = info.find_element(By.CSS_SELECTOR, "h3.product-title a")
                name = a.text.strip()
                if not name:
                    continue
                had_name += 1

                href = a.get_attribute("href")
                link = href if (href and href.startswith("http")) else (
                    "https://www.croma.com" + href if href else url
                )

                price = None
                for sel in ["span.amount.plp-srp-new-amount", "div.new-price span.amount", "span.amount"]:
                    try:
                        price_text = info.find_element(By.CSS_SELECTOR, sel).get_attribute("textContent").strip()
                        price = clean_price(price_text)
                        if price:
                            break
                    except:
                        continue

                if not price:
                    try:
                        card_for_price = info.find_element(By.XPATH, "..")
                        price_el = card_for_price.find_element(
                            By.XPATH, ".//*[contains(normalize-space(text()), '₹')]"
                        )
                        price = clean_price(price_el.get_attribute("textContent").strip().split("\n")[0])
                    except:
                        pass

                if not price:
                    continue
                had_price += 1

                image = DEFAULT_IMAGE
                try:
                    card = info.find_element(By.XPATH, "..")
                    img = card.find_element(By.CSS_SELECTOR, "div[data-testid='product-img'] img, img")
                    image = get_image_src(img)
                except:
                    pass

                key = (name, price)
                if key not in seen:
                    seen.add(key)
                    results.append({"site": "Croma", "name": name, "price": price, "link": link, "image": image})
            except Exception:
                continue

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if not href or "/searchB" in href:
                    continue
                link = href if href.startswith("http") else "https://www.croma.com" + href

                name = a.text.strip()
                price = None
                image = DEFAULT_IMAGE

                card = a
                for _ in range(8):
                    try:
                        card = card.find_element(By.XPATH, "..")
                    except:
                        break

                    if not name:
                        try:
                            best_line = ""
                            for line in card.text.strip().split("\n"):
                                line = line.strip()
                                if line and not is_junk_line(line) and len(line) > len(best_line):
                                    best_line = line
                            if best_line:
                                name = best_line
                        except:
                            pass

                    if price is None:
                        try:
                            price_el = card.find_element(
                                By.XPATH, ".//*[contains(normalize-space(text()), '₹')]"
                            )
                            price = clean_price(price_el.get_attribute("textContent").strip().split("\n")[0])
                        except:
                            pass

                    if image == DEFAULT_IMAGE:
                        try:
                            img = card.find_element(By.TAG_NAME, "img")
                            image = get_image_src(img)
                        except:
                            pass

                    if name and price:
                        break

                if not name or not price:
                    continue

                key = (name, price)
                if key not in seen:
                    seen.add(key)
                    had_name += 1
                    had_price += 1
                    results.append({"site": "Croma", "name": name, "price": price, "link": link, "image": image})
            except Exception:
                continue

    except Exception as e:
        print("Croma Error:", e)

    safe_quit(driver)
    print(f"Croma: {had_name} blocks had a name, {had_price} had a price")
    print(f"Croma: returning {len(results)} products for '{query}'")
    return results


def search_reliancedigital(query):
    driver = get_driver()
    results = []
    try:
        driver.get("https://www.reliancedigital.in/")

        try:
            search_box = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='search'], input[placeholder*='Search']"))
            )
        except Exception:
            print("Reliance Digital: search box never appeared")
            safe_quit(driver)
            return []

        search_box.send_keys(query)
        search_box.send_keys(Keys.ENTER)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.details-container"))
            )
        except Exception:
            print(f"Reliance Digital DEBUG: no a.details-container appeared for '{query}'. "
                  f"page_source length = {len(driver.page_source)}")

        scroll_full_page(driver, passes=4)
        time.sleep(1.5)

        cards = driver.find_elements(By.CSS_SELECTOR, "a.details-container")
        print(f"Reliance Digital: found {len(cards)} cards for '{query}'")

        seen = set()
        for card in cards:
            try:
                name = card.find_element(By.CSS_SELECTOR, "div.product-card-title").text.strip()
            except:
                continue

            try:
                price_text = card.find_element(By.CSS_SELECTOR, "div.price").text.strip()
                price = clean_price(price_text)
            except:
                continue

            if not price or not name:
                continue

            key = (name, price)
            if key in seen:
                continue
            seen.add(key)

            link = card.get_attribute("href") or driver.current_url

            image = DEFAULT_IMAGE
            try:
                img = card.find_element(By.CSS_SELECTOR, "img")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img)
                time.sleep(0.1)
                image = get_image_src(img)
            except:
                pass

            if image == DEFAULT_IMAGE:
                try:
                    product_card = card.find_element(
                        By.XPATH, "./ancestor::div[contains(@class,'product-card') or contains(@class,'gridItem')][1]"
                    )
                    img = product_card.find_element(By.CSS_SELECTOR, "img")
                    image = get_image_src(img)
                except:
                    pass

            results.append({"site": "Reliance Digital", "name": name, "price": price, "link": link, "image": image})
    except Exception as e:
        print("Reliance Digital error:", e)

    safe_quit(driver)
    print(f"Reliance Digital: returning {len(results)} products for '{query}'")
    return results


def search_jiomart(query):
    driver = get_driver()
    url = f"https://www.jiomart.com/products?q={query.replace(' ', '%20')}"
    results = generic_price_scan(driver, url, "JioMart")
    safe_quit(driver)
    return results


def search_bigbasket(query):
    driver = get_driver()
    url = f"https://www.bigbasket.com/ps/?q={query.replace(' ', '+')}"
    results = generic_price_scan(driver, url, "BigBasket", price_tag="span")
    safe_quit(driver)
    return results


def search_zepto(query):
    driver = get_driver()
    url = f"https://www.zeptonow.com/search?query={query.replace(' ', '%20')}"
    results = generic_price_scan(driver, url, "Zepto")
    safe_quit(driver)
    return results


def search_blinkit(query):
    driver = get_driver()
    url = f"https://blinkit.com/s/?q={query.replace(' ', '%20')}"
    results = generic_price_scan(driver, url, "Blinkit")
    safe_quit(driver)
    return results


GROCERY_KEYWORDS = [
    "milk", "rice", "atta", "flour", "oil", "sugar", "salt", "maggi", "noodles",
    "biscuit", "snacks", "tea", "coffee", "soap", "shampoo", "vegetable", "fruit",
    "grocery", "dal", "pulses", "ghee", "butter", "bread", "egg", "paneer",
    "detergent", "cleaner", "toothpaste", "juice", "water", "chips", "namkeen", "cheese",
    "masala", "spice", "spices", "curd", "yogurt", "diaper", "baby food",
    "baby wipes", "pet food", "dog food", "cat food", "dishwash", "phenyl",
]

FASHION_KEYWORDS = [
    "shirt", "shoes", "jeans", "dress", "saree", "kurti", "t-shirt", "tshirt",
    "jacket", "footwear", "sneakers", "sandals", "heels", "top", "trouser",
    "skirt", "suit", "kurta", "lehenga", "watch", "belt", "nike", "adidas",
    "puma", "reebok",
    "sportswear", "innerwear", "ethnic wear", "backpack", "sling bag",
    "slipper", "flip flop", "running shoes", "formal shoes", "casual shoes",
]

ACCESSORY_KEYWORDS = [
    "case", "cover", "pouch", "stand", "charger", "cable", "strap",
    "guard", "protector", "skin", "holder", "mount", "adapter", "sleeve", "bag", "power bank"
]

QUERY_NORMALIZATION = {
    "phone": "mobile phone",
    "smartphone": "mobile phone",
    "ear buds": "earbuds",
    "ear phones": "earphones",
    "head set": "headphones",
    "headset": "headphones",
    "shoe": "shoes",
    "tv": "smart tv",
    "fridge": "refrigerator",
    "ac": "air conditioner",
    "laptop bag": "laptop bag",
}

PRODUCT_VOCABULARY = [
    "apple", "iphone", "samsung", "galaxy", "oneplus", "vivo", "oppo", "xiaomi", "redmi",
    "realme", "motorola", "nokia", "google", "pixel", "asus", "acer", "dell", "hp", "lenovo",
    "msi", "macbook", "sony", "lg", "panasonic", "whirlpool", "haier", "godrej", "voltas",
    "daikin", "bluestar", "boat", "jbl", "bose", "sennheiser", "noise", "fireboltt", "titan",
    "canon", "nikon", "gopro", "playstation", "xbox", "nintendo",
    "nike", "adidas", "puma", "reebok", "levis", "zara", "woodland", "bata", "skechers", "crocs",
    "mobile", "mobiles", "phone", "phones", "smartphone", "smartphones", "laptop", "laptops",
    "tablet", "tablets", "television", "tv", "tvs", "headphone", "headphones", "earbud",
    "earbuds", "earphone", "earphones", "speaker", "speakers", "charger", "chargers",
    "powerbank", "keyboard", "keyboards", "mouse", "monitor", "monitors", "camera", "cameras",
    "watch", "watches", "smartwatch", "smartwatches", "refrigerator", "fridge", "washing",
    "machine", "airconditioner", "conditioner", "shirt", "shirts", "tshirt", "tshirts",
    "jeans", "dress", "dresses", "saree", "sarees", "kurta", "kurtas", "shoe", "shoes",
    "sneaker", "sneakers", "sandal", "sandals", "slipper", "slippers", "bluetooth",
    "wireless", "wired", "rice", "atta", "flour", "milk", "butter", "cheese", "biscuit",
    "biscuits", "chips", "snacks", "namkeen",
    "printer", "printers", "router", "routers", "webcam", "webcams", "backpack",
    "backpacks", "kurti", "kurtis", "innerwear", "sportswear", "diaper", "diapers",
    "detergent", "ghee", "dal", "pulses", "masala", "spices", "hdmi", "pendrive",
    "ssd", "hdd", "powerbank",
]


def fuzzy_correct_word(word):
    lower = word.lower()
    if lower in PRODUCT_VOCABULARY:
        return word
    matches = difflib.get_close_matches(lower, PRODUCT_VOCABULARY, n=1, cutoff=0.72)
    if matches:
        corrected = matches[0]
        return corrected.capitalize() if word[:1].isupper() else corrected
    return word


def normalize_query(query):
    q = query.strip()
    if not q:
        return q

    lower = q.lower()
    if lower in QUERY_NORMALIZATION:
        return QUERY_NORMALIZATION[lower]

    corrected_words = [fuzzy_correct_word(w) for w in q.split()]
    corrected = " ".join(corrected_words)
    corrected = re.sub(r"\biphone\b", "iPhone", corrected, flags=re.I)
    return corrected


def _has_any(text, phrases):
    for p in phrases:
        if len(p) <= 3 and p.isalpha():
            if re.search(r"\b" + re.escape(p) + r"\b", text):
                return True
        else:
            if p in text:
                return True
    return False


SUBCATEGORY_RULES = {
    "mobiles": {
        "allow": ["iphone", "galaxy", "oneplus", "xiaomi", "redmi", "motorola", "pixel",
                  "smartphone", "mobile phone", "mobile", "phone"],
        "reject": ["case", "cover", "charger", "earbud", "earphone", "headphone",
                   "smartwatch", "smart watch", "watch", "fit", "band", "buds", "tab",
                   "ring", "tablet", "laptop", "cable",
                   "power bank", "strap", "screen guard", "screen protector"],
    },
    "laptops": {
        "allow": ["laptop", "notebook", "chromebook", "macbook"],
        "reject": ["laptop bag", "laptop sleeve", "laptop mouse", "keyboard",
                   "monitor", "desktop", "tablet", "laptop charger", "laptop cover",
                   "laptop stand", "cooling pad", "bag", "backpack"],
    },
    "tablets": {
        "allow": ["tablet", "tab", "ipad"],
        "reject": ["case", "cover", "keyboard", "stylus", "screen protector",
                   "charger", "phone"],
    },
    "tvs": {
        "allow": ["tv", "television", "smart tv", "led tv", "qled", "oled"],
        "reject": ["wall mount", "tv remote", "soundbar", "monitor", "projector",
                   "refrigerator", "tv stand", "tv unit", "phone", "mobile"],
    },
    "refrigerators": {
        "allow": ["refrigerator", "fridge", "double door", "single door",
                  "side-by-side", "side by side", "french door"],
        "reject": ["washing machine", "microwave", "air conditioner", "water purifier"],
    },
    "ac": {
        "allow": ["air conditioner", "split ac", "window ac", "inverter ac", "ac"],
        "reject": ["air cooler", "refrigerator", "fan", "air purifier"],
    },
    "washing_machines": {
        "allow": ["washing machine", "washer"],
        "reject": ["refrigerator", "air conditioner", "dishwasher", "dryer"],
    },
    "monitors": {
        "allow": ["monitor"],
        "reject": ["laptop", "television", "tv", "projector", "monitor stand", "monitor arm"],
    },
    "cameras": {
        "allow": ["camera", "dslr", "mirrorless", "webcam"],
        "reject": ["camera bag", "camera tripod", "phone", "cctv"],
    },
    "watches": {
        "allow": ["watch"],
        "reject": ["analog watch", "digital watch", "watch strap", "phone", "shoes"],
    },
    "smart_watches": {
        "allow": ["smartwatch", "smart watch"],
        "reject": ["phone", "mobile", "shoes", "analog watch"],
    },
    "gaming": {
        "allow": ["playstation", "xbox", "nintendo", "gaming console", "gaming pc",
                  "gaming laptop", "gaming monitor", "gaming keyboard", "gaming mouse",
                  "gaming headset", "gaming controller", "graphics card"],
        "reject": ["gaming chair", "gaming table", "gaming t-shirt", "gaming toy", "toy"],
    },
    "audio": {
        "allow": ["earbud", "earphone", "headphone", "bluetooth speaker",
                  "soundbar", "home theatre", "home theater", "speaker"],
        "reject": ["phone", "laptop", "television", "tv", "speaker stand"],
    },
    "printers": {
        "allow": ["printer", "inkjet printer", "laser printer", "all-in-one printer"],
        "reject": ["ink cartridge", "toner cartridge"],
    },
    "networking": {
        "allow": ["router", "wifi router", "modem", "range extender",
                  "access point", "network switch"],
        "reject": ["gaming switch"],
    },
    "computer_components": {
        "allow": ["graphics card", "gpu", "processor", "cpu", "motherboard", "ram",
                  "cabinet", "smps", "power supply", "computer component"],
        "reject": ["laptop", "gaming console"],
    },
    "mobile_cases_covers": {
        "allow": ["case", "cover", "mobile case", "phone case", "back cover"],
        "reject": ["laptop", "tablet case"],
    },
    "chargers": {
        "allow": ["charger", "charging adapter", "fast charger"],
        "reject": ["power bank"],
    },
    "usb_cables": {
        "allow": ["usb cable", "type-c cable", "type c cable", "lightning cable", "data cable"],
        "reject": ["hdmi cable"],
    },
    "power_banks": {
        "allow": ["power bank", "powerbank"],
        "reject": [],
    },
    "earphones": {
        "allow": ["earphone", "earphones"],
        "reject": ["earbud", "tws", "headphone", "speaker"],
    },
    "headphones": {
        "allow": ["headphone", "headphones", "headset"],
        "reject": ["earbud", "tws", "earphone", "speaker"],
    },
    "tws_earbuds": {
        "allow": ["earbud", "earbuds", "tws", "true wireless"],
        "reject": ["headphone", "earphone", "speaker"],
    },
    "bluetooth_speakers": {
        "allow": ["bluetooth speaker", "speaker", "soundbar"],
        "reject": ["earbud", "headphone", "earphone"],
    },
    "laptop_bags": {
        "allow": ["laptop bag", "laptop backpack", "laptop sleeve"],
        "reject": ["mouse", "keyboard"],
    },
    "mouse": {
        "allow": ["mouse"],
        "reject": ["laptop"],
    },
    "keyboards": {
        "allow": ["keyboard", "keyboards"],
        "reject": ["mouse", "laptop"],
    },
    "webcams": {
        "allow": ["webcam", "web camera"],
        "reject": ["dslr", "mirrorless", "cctv"],
    },
    "hdmi_cables": {
        "allow": ["hdmi cable", "hdmi"],
        "reject": ["usb cable"],
    },
    "memory_cards": {
        "allow": ["memory card", "sd card", "microsd", "micro sd"],
        "reject": ["pen drive", "ssd", "hdd"],
    },
    "pen_drives": {
        "allow": ["pen drive", "pendrive", "usb drive", "flash drive"],
        "reject": ["memory card", "ssd", "hdd"],
    },
    "ssd_hdd": {
        "allow": ["ssd", "hdd", "hard disk", "solid state drive", "hard drive"],
        "reject": ["pen drive", "memory card"],
    },
    "power_strips": {
        "allow": ["power strip", "extension board", "surge protector"],
        "reject": [],
    },
    "smart_home_accessories": {
        "allow": ["smart home", "smart plug", "smart bulb", "smart light",
                  "smart switch", "alexa", "google home"],
        "reject": [],
    },
    "men": {
        "allow": ["men", "men's", "mens"],
        "reject": ["women", "women's", "kids", "girls", "boys"],
    },
    "women": {
        "allow": ["women", "women's", "womens", "ladies"],
        "reject": ["men's", "mens", "kids", "boys"],
    },
    "kids": {
        "allow": ["kids", "boys", "girls", "children"],
        "reject": [],
    },
    "tshirts": {
        "allow": ["t-shirt", "tshirt", "tee"],
        "reject": [],
    },
    "shirts": {
        "allow": ["shirt"],
        "reject": ["t-shirt", "tshirt"],
    },
    "jeans": {
        "allow": ["jeans", "denim"],
        "reject": [],
    },
    "trousers": {
        "allow": ["trouser", "trousers", "pants", "chinos"],
        "reject": ["jeans"],
    },
    "dresses": {
        "allow": ["dress", "dresses", "gown"],
        "reject": [],
    },
    "sarees": {
        "allow": ["saree", "sarees", "sari"],
        "reject": [],
    },
    "kurtis": {
        "allow": ["kurti", "kurtis"],
        "reject": [],
    },
    "ethnic_wear": {
        "allow": ["ethnic", "kurta", "lehenga", "salwar", "sherwani", "dupatta"],
        "reject": [],
    },
    "sportswear": {
        "allow": ["sportswear", "sports wear", "track pants", "gym wear",
                  "activewear", "jersey"],
        "reject": [],
    },
    "jackets": {
        "allow": ["jacket", "jackets", "hoodie", "sweatshirt", "blazer"],
        "reject": [],
    },
    "innerwear": {
        "allow": ["innerwear", "underwear", "briefs", "boxers", "bra", "vest", "lingerie"],
        "reject": [],
    },
    "sneakers": {
        "allow": ["sneaker", "sneakers"],
        "reject": ["running shoe", "running shoes", "formal shoe", "sandal", "slipper"],
    },
    "running_shoes": {
        "allow": ["running shoe", "running shoes", "running"],
        "reject": ["sneaker", "formal shoe", "sandal", "slipper"],
    },
    "casual_shoes": {
        "allow": ["casual shoe", "casual shoes"],
        "reject": ["running shoe", "formal shoe", "sneaker", "sandal", "slipper"],
    },
    "formal_shoes": {
        "allow": ["formal shoe", "formal shoes"],
        "reject": ["casual shoe", "running shoe", "sneaker", "sandal", "slipper"],
    },
    "sandals": {
        "allow": ["sandal", "sandals"],
        "reject": ["slipper", "shoe", "shoes", "sneaker"],
    },
    "slippers": {
        "allow": ["slipper", "slippers", "flip flop", "flip-flop"],
        "reject": ["sandal", "shoe", "sneaker"],
    },
    "bags_backpacks": {
        "allow": ["bag", "backpack", "handbag", "tote", "sling bag", "duffel"],
        "reject": [],
    },
    "fruits_vegetables": {
        "allow": ["fruit", "fruits", "vegetable", "vegetables"],
        "reject": ["juice", "pickle", "chips"],
    },
    "dairy_eggs": {
        "allow": ["milk", "curd", "yogurt", "paneer", "cheese", "butter", "egg", "eggs"],
        "reject": [],
    },
    "rice_atta_grains": {
        "allow": ["rice", "atta", "flour", "wheat", "grain", "grains", "basmati", "poha", "suji", "rava"],
        "reject": [],
    },
    "pulses_dal": {
        "allow": ["dal", "pulses", "lentil", "moong", "toor", "chana", "rajma", "urad"],
        "reject": [],
    },
    "cooking_oil_ghee": {
        "allow": ["oil", "ghee", "cooking oil", "sunflower oil", "mustard oil", "olive oil"],
        "reject": ["hair oil", "massage oil"],
    },
    "snacks_biscuits": {
        "allow": ["biscuit", "biscuits", "chips", "namkeen", "snacks", "cookies", "wafers"],
        "reject": [],
    },
    "beverages": {
        "allow": ["tea", "coffee", "juice", "soft drink", "soda", "beverage", "drink"],
        "reject": ["milk"],
    },
    "masalas_spices": {
        "allow": ["masala", "spice", "spices", "turmeric", "chilli powder", "garam masala"],
        "reject": [],
    },
    "instant_packaged_food": {
        "allow": ["noodles", "maggi", "instant", "ready to eat", "pasta", "soup"],
        "reject": [],
    },
    "personal_care": {
        "allow": ["shampoo", "soap", "toothpaste", "lotion", "deodorant",
                  "face wash", "conditioner"],
        "reject": [],
    },
    "household_cleaning": {
        "allow": ["detergent", "cleaner", "phenyl", "toilet cleaner", "dishwash"],
        "reject": [],
    },
    "baby_care": {
        "allow": ["diaper", "diapers", "baby food", "baby wipes", "infant"],
        "reject": [],
    },
    "pet_supplies": {
        "allow": ["pet food", "dog food", "cat food", "pet supplies"],
        "reject": [],
    },
    "covers": {
        "allow": ["case", "cover", "mobile case", "phone case", "back cover"],
        "reject": ["laptop", "tablet case"],
    },
    "powerbanks": {
        "allow": ["power bank", "powerbank"],
        "reject": [],
    },
    "cables": {
        "allow": ["cable", "usb cable", "type-c cable", "type c cable",
                  "lightning cable", "hdmi cable", "data cable"],
        "reject": [],
    },
    "footwear": {
        "allow": ["shoe", "shoes", "sneaker", "sneakers", "sandal", "sandals",
                  "slipper", "slippers", "footwear"],
        "reject": [],
    },
    "staples": {
        "allow": ["rice", "atta", "flour", "wheat", "grain", "grains",
                  "basmati", "dal", "pulses"],
        "reject": [],
    },
    "dairy": {
        "allow": ["milk", "curd", "yogurt", "paneer", "cheese", "butter", "egg", "eggs"],
        "reject": [],
    },
    "snacks": {
        "allow": ["biscuit", "biscuits", "chips", "namkeen", "snacks", "cookies", "wafers"],
        "reject": [],
    },
}


def passes_subcategory(name, subcategory):
    if not subcategory or subcategory not in SUBCATEGORY_RULES:
        return True
    name_lower = name.lower()
    rules = SUBCATEGORY_RULES[subcategory]
    if _has_any(name_lower, rules["reject"]):
        return False
    if rules["allow"] and not _has_any(name_lower, rules["allow"]):
        return False
    return True


BRAND_LIST = [
    "apple", "samsung", "oneplus", "vivo", "oppo", "xiaomi", "redmi", "realme",
    "motorola", "nokia", "google", "asus", "acer", "dell", "hp", "lenovo", "msi",
    "sony", "lg", "panasonic", "whirlpool", "haier", "godrej", "voltas", "daikin",
    "bluestar", "boat", "jbl", "bose", "sennheiser", "noise", "fireboltt", "titan",
    "canon", "nikon", "gopro", "nike", "adidas", "puma", "reebok", "levis", "zara",
    "woodland", "bata", "skechers", "crocs",
]

CATEGORY_DEFS = {
    "mobile": {
        "synonyms": ["phone", "smartphone", "mobile", "iphone", "galaxy"],
        "reject": ["smartwatch", "smart watch", "watch", "fit", "band", "buds", "tab",
                   "ring", "earbud", "earphone",
                   "headphone", "headset", "tablet", "ipad", "laptop", "notebook",
                   "tv", "television", "refrigerator", "washing machine",
                   "air conditioner", "case", "cover", "charger",
                   "cable", "power bank"],
    },
    "tv": {
        "synonyms": ["tv", "television", "smart tv", "led tv", "qled", "oled"],
        "reject": ["phone", "mobile", "watch", "refrigerator", "washing machine",
                   "air conditioner", "monitor", "soundbar", "remote"],
    },
    "laptop": {
        "synonyms": ["laptop", "notebook", "chromebook", "macbook"],
        "reject": ["mouse", "keyboard", "bag", "sleeve", "charger", "cover",
                   "monitor", "desktop", "tablet", "phone"],
    },
    "watch": {
        "synonyms": ["watch", "smartwatch", "smart watch"],
        "reject": ["phone", "mobile", "tv", "laptop", "tablet", "shoes", "strap"],
    },
    "earbuds": {
        "synonyms": ["earbuds", "earbud", "tws", "wireless earbuds", "earphone", "earphones"],
        "reject": ["phone", "mobile", "laptop", "tv", "watch", "speaker"],
    },
    "headphones": {
        "synonyms": ["headphone", "headphones", "headset"],
        "reject": ["phone", "mobile", "laptop", "tv", "watch"],
    },
    "refrigerator": {
        "synonyms": ["refrigerator", "fridge"],
        "reject": ["washing machine", "air conditioner", "microwave"],
    },
    "washing machine": {
        "synonyms": ["washing machine", "washer"],
        "reject": ["refrigerator", "air conditioner", "microwave"],
    },
    "ac": {
        "synonyms": ["air conditioner", "ac", "split ac", "window ac"],
        "reject": ["refrigerator", "air cooler", "fan", "air purifier"],
    },
    "camera": {
        "synonyms": ["camera", "dslr", "mirrorless", "webcam"],
        "reject": ["phone", "mobile", "cctv"],
    },
    "shoes": {
        "synonyms": ["shoes", "sneakers", "sandals", "footwear"],
        "reject": ["watch", "bag", "shirt", "t-shirt", "jeans"],
    },
}


def detect_brand(query):
    q_lower = query.lower()
    for brand in BRAND_LIST:
        if re.search(r"\b" + re.escape(brand) + r"\b", q_lower):
            return brand.title()
    return None


def detect_category(query):
    q_lower = query.lower()
    all_matches = []
    for category, rules in CATEGORY_DEFS.items():
        for syn in rules["synonyms"]:
            if _has_any(q_lower, [syn]):
                all_matches.append((len(syn), category))
    if not all_matches:
        return None
    all_matches.sort(reverse=True)
    return all_matches[0][1]


def passes_category_relevance(name, category):
    if not category or category not in CATEGORY_DEFS:
        return True
    name_lower = name.lower()
    rules = CATEGORY_DEFS[category]
    if _has_any(name_lower, rules["reject"]):
        return False
    return True


SECTION_GROCERY = "grocery"
SECTION_ELECTRONICS = "electronics"
SECTION_ELECTRONICS_ACCESSORIES = "electronics_accessories"
SECTION_FASHION = "fashion"

SECTION_STORE_MAP = {
    SECTION_GROCERY: ["BigBasket", "JioMart"],
    SECTION_ELECTRONICS: ["Amazon", "Flipkart", "Croma", "Reliance Digital"],
    SECTION_ELECTRONICS_ACCESSORIES: ["Amazon", "Flipkart", "Croma", "Reliance Digital"],
    SECTION_FASHION: ["Myntra", "Flipkart", "Amazon"],
}

SECTION_SCRAPER_FUNCS = {
    SECTION_GROCERY: [search_bigbasket, search_jiomart],
    SECTION_ELECTRONICS: [search_amazon, search_flipkart, search_croma, search_reliancedigital],
    SECTION_ELECTRONICS_ACCESSORIES: [search_amazon, search_flipkart, search_croma, search_reliancedigital],
    SECTION_FASHION: [search_myntra, search_flipkart, search_amazon],
}


def search_products(query, subcategory=None, section=None, limit=10):
    normalized = normalize_query(query)
    detected_brand = detect_brand(normalized)
    detected_category = detect_category(normalized)
    print(f"\nQuery: {query}")
    print(f"Normalized Query: {normalized}")
    print(f"Section: {section or '(none — using keyword guess)'}")
    print(f"Detected Brand: {detected_brand or '—'}")
    print(f"Detected Category: {detected_category or '—'}")

    def safe_call(fn, *args, retries=1):
        attempt = 0
        while True:
            try:
                return fn(*args)
            except (InvalidSessionIdException, WebDriverException) as e:
                if attempt < retries:
                    attempt += 1
                    print(f"{fn.__name__}: browser session crashed ({type(e).__name__}) — retrying ({attempt}/{retries})...")
                    time.sleep(1.5)
                    continue
                print(f"{fn.__name__} failed after retry:", e)
                return []
            except Exception as e:
                print(f"{fn.__name__} failed:", e)
                return []

    def run_search(q, section=section):
        if section and section in SECTION_SCRAPER_FUNCS:
            fns = SECTION_SCRAPER_FUNCS[section]
        else:
            q_lower = q.lower()
            is_grocery = any(word in q_lower for word in GROCERY_KEYWORDS)
            is_fashion = any(word in q_lower for word in FASHION_KEYWORDS)
            if is_grocery:
                fns = [search_bigbasket, search_jiomart]
            elif is_fashion:
                fns = [search_myntra, search_flipkart, search_amazon]
            else:
                fns = [search_amazon, search_flipkart, search_croma, search_reliancedigital]

        # Railway's RAM budget can't hold several simultaneous headless
        # Chrome instances (this is what was causing WORKER TIMEOUT ->
        # SIGKILL in production) — run sequentially there. Locally, run
        # in parallel for speed.
        if IS_PRODUCTION:
            all_results = []
            for fn in fns:
                r = safe_call(fn, q)
                print(f"{fn.__name__}: {len(r)} products")
                all_results += r
        else:
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(fns)) as executor:
                future_to_fn = {executor.submit(safe_call, fn, q): fn for fn in fns}
                for future in concurrent.futures.as_completed(future_to_fn):
                    fn = future_to_fn[future]
                    r = future.result()
                    print(f"{fn.__name__}: {len(r)} products")
                    all_results += r

        print(f"Total (before filtering): {len(all_results)}")
        return all_results

    def filter_and_dedupe(results, q):
        query_words = [w.lower() for w in q.split() if len(w) > 2]
        query_has_accessory_word = any(word in query_words for word in ACCESSORY_KEYWORDS)

        def word_matches(word, name_lower):
            if word in name_lower:
                return True
            if word.endswith("s") and word[:-1] in name_lower:
                return True
            if (word + "s") in name_lower:
                return True
            return False

        def keyword_present(keyword, text):
            if " " in keyword:
                return keyword in text
            return re.search(r"\b" + re.escape(keyword) + r"\b", text) is not None

        filtered = []
        seen = set()
        for item in results:
            item_name_lower = item["name"].lower()
            matches_query = any(word_matches(w, item_name_lower) for w in query_words) if query_words else True
            is_accessory = any(keyword_present(word, item_name_lower) for word in ACCESSORY_KEYWORDS)

            if not matches_query:
                print(f"REJECTED [{item['site']}]: {item['name']}  (₹{item['price']})")
                print(f"  Reason: name doesn't contain any query word {query_words}")
                continue
            if is_accessory and not query_has_accessory_word:
                print(f"REJECTED [{item['site']}]: {item['name']}  (₹{item['price']})")
                print(f"  Reason: looks like an accessory, query wasn't an accessory search")
                continue

            if matches_query and (query_has_accessory_word or not is_accessory):
                if not passes_subcategory(item["name"], subcategory):
                    print(f"REJECTED [{item['site']}]: {item['name']}  (₹{item['price']})")
                    print(f"  Reason: subcategory '{subcategory}' rules — "
                          f"missing an allow-word or hit a reject-word")
                    continue
                if not passes_category_relevance(item["name"], detected_category):
                    print(f"REJECTED [{item['site']}]: {item['name']}  (₹{item['price']})")
                    print(f"  Reason: query category is '{detected_category}', "
                          f"product looks like a different category")
                    continue
                dedup_key = (item["site"], item_name_lower, item["price"])
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                item["logo"] = SITE_LOGOS.get(item["site"], DEFAULT_IMAGE)
                filtered.append(item)
        return filtered

    all_results = run_search(normalized)
    filtered_results = filter_and_dedupe(all_results, normalized)

    def log_scraped_vs_relevant(scraped, relevant):
        scraped_by_site = {}
        relevant_by_site = {}
        for item in scraped:
            scraped_by_site[item["site"]] = scraped_by_site.get(item["site"], 0) + 1
        for item in relevant:
            relevant_by_site[item["site"]] = relevant_by_site.get(item["site"], 0) + 1
        for site in scraped_by_site:
            print(f"{site}: {scraped_by_site[site]} scraped → {relevant_by_site.get(site, 0)} relevant")

    log_scraped_vs_relevant(all_results, filtered_results)

    def top_up_short_sites(filtered, q, section):
        if not section or section not in SECTION_STORE_MAP:
            return filtered
        expected_stores = SECTION_STORE_MAP[section]
        counts = {}
        for item in filtered:
            counts[item["site"]] = counts.get(item["site"], 0) + 1

        short_stores = [s for s in expected_stores if counts.get(s, 0) < SITE_SECTION_CAPS.get(s, 10)]
        if not short_stores:
            return filtered

        fn_by_site = {
            "Amazon": search_amazon, "Flipkart": search_flipkart,
            "Croma": search_croma, "Reliance Digital": search_reliancedigital,
            "Myntra": search_myntra, "JioMart": search_jiomart, "BigBasket": search_bigbasket,
        }

        trimmed_q = q
        if len(trimmed_q.split()) > 1:
            trimmed_q = " ".join(trimmed_q.split()[:-1])

        seen_keys = {(it["site"], it["name"].lower(), it["price"]) for it in filtered}
        for site in short_stores:
            fn = fn_by_site.get(site)
            if not fn:
                continue
            print(f"Top-up: {site} short of cap ({counts.get(site, 0)}/{SITE_SECTION_CAPS.get(site, 10)}) — retrying with '{trimmed_q}'")
            extra_raw = safe_call(fn, trimmed_q)
            extra_relevant = filter_and_dedupe(extra_raw, trimmed_q)
            added = 0
            for item in extra_relevant:
                if item["site"] != site:
                    continue
                key = (item["site"], item["name"].lower(), item["price"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                filtered.append(item)
                added += 1
            print(f"Top-up: {site} +{added} products")
        return filtered

    if section:
        filtered_results = top_up_short_sites(filtered_results, normalized, section)

    fallback_query = normalized
    while not filtered_results and len(fallback_query.split()) > 1:
        fallback_query = " ".join(fallback_query.split()[:-1])
        print(f"Fallback Query: {fallback_query}")
        more_results = run_search(fallback_query)
        filtered_results = filter_and_dedupe(more_results, fallback_query)

    filtered_results.sort(key=lambda x: x["price"])
    print(f"Total (final, relevant, deduped): {len(filtered_results)}\n")
    return filtered_results if limit is None else filtered_results[:limit]


SITE_SECTION_CAPS = {
    "Flipkart": 3,
    "Amazon": 3,
    "Croma": 2,
    "Reliance Digital": 2,
    "Myntra": 4,
    "JioMart": 6,
    "BigBasket": 6,
}

ELECTRONICS_STORES = ["Amazon", "Flipkart", "Croma", "Reliance Digital"]
FASHION_STORES = ["Myntra", "Flipkart", "Amazon"]
GROCERY_STORES = ["BigBasket", "JioMart"]


def get_expected_stores(query, section=None):
    if section and section in SECTION_STORE_MAP:
        return SECTION_STORE_MAP[section]
    q_lower = query.lower()
    if any(w in q_lower for w in GROCERY_KEYWORDS):
        return GROCERY_STORES
    elif any(w in q_lower for w in FASHION_KEYWORDS):
        return FASHION_STORES
    return ELECTRONICS_STORES


def rank_and_group(all_relevant_results, query, section=None):
    expected_stores = get_expected_stores(query, section)
    all_sorted = sorted(all_relevant_results, key=lambda x: x["price"])

    site_sections = []
    combined = []
    seen = set()
    for site in expected_stores:
        cap = SITE_SECTION_CAPS.get(site, 10)
        site_items = [p for p in all_sorted if p["site"] == site][:cap]
        site_sections.append({"site": site, "products": site_items})
        for p in site_items:
            key = (p["site"], p["name"], p["price"])
            if key not in seen:
                seen.add(key)
                combined.append(p)

    combined.sort(key=lambda x: x["price"])

    rank_lookup = {}
    ranked = []
    for i, item in enumerate(combined):
        item_copy = dict(item)
        item_copy["rank"] = i + 1
        ranked.append(item_copy)
        rank_lookup[(item["site"], item["name"], item["price"])] = i + 1

    for section_group in site_sections:
        section_group["products"] = [
            {**p, "rank": rank_lookup.get((p["site"], p["name"], p["price"]))}
            for p in section_group["products"]
        ]

    return ranked, site_sections


def search_products_ranked(query, subcategory=None, section=None):
    normalized = normalize_query(query)
    full_results = search_products(query, subcategory=subcategory, section=section, limit=None)
    ranked, site_sections = rank_and_group(full_results, normalized, section=section)
    return ranked, site_sections