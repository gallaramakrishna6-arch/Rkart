from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

options = Options()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

driver.get("https://www.amazon.in/s?k=nike+shoes")
time.sleep(4)

products = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
print(f"\n{len(products)} products found\n")

for product in products[:5]:
    try:
        img = product.find_element(By.CSS_SELECTOR, "img.s-image")
        src = img.get_attribute("src")
        print("IMAGE SRC:", src)
    except Exception as e:
        print("IMAGE ERROR:", e)

driver.quit()
input("Press Enter to close...")