from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

def check_site(url, name):
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    print(f"\n{name} తెరుస్తోంది: {url}")
    driver.get(url)
    print(f"{name} పేజీ 8 సెకన్లు తెరిచి ఉంటుంది — స్క్రీన్ మీద ఏం కనిపిస్తుందో చూడు...")
    time.sleep(8)

    print(f"{name} పేజీ టైటిల్: {driver.title}")
    print(f"{name} ప్రస్తుత URL: {driver.current_url}")

    driver.quit()


if __name__ == "__main__":
    check_site("https://www.flipkart.com/search?q=nike+shoes", "Flipkart")
    check_site("https://www.myntra.com/nike-shoes", "Myntra")