import time
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

# --- Setup SQLite Database ---
conn = sqlite3.connect('zer4u_products33.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT,
    price TEXT,
    img_url TEXT,
    page INTEGER
)
''')
conn.commit()

# --- Setup Selenium WebDriver ---
service = Service()  # Optionally, specify the path to chromedriver if needed
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Run headless (without opening a browser window)
driver = webdriver.Chrome(service=service, options=options)

page = 1
while True:
    # Construct URL with current page number (bscrp parameter)
    url = f"https://www.zer4u.co.il/%D7%96%D7%A8%D7%99_%D7%A4%D7%A8%D7%97%D7%99%D7%9D?bscrp={page}"
    print(f"Processing page: {page} - {url}")
    driver.get(url)
    time.sleep(3)  # Wait for the page to fully load

    # Find all product containers on the page
    product_containers = driver.find_elements(By.CSS_SELECTOR, "div.product_in_list")
    
    # If no products are found, assume we've reached the end.
    if not product_containers:
        print(f"No products found on page {page}. Stopping the loop.")
        break

    # Loop through each product container
    for container in product_containers:
        # Scroll container into view (helps lazy loading)
        driver.execute_script("arguments[0].scrollIntoView();", container)
        
        # --- Extract the image URL, waiting for lazy loading to complete ---
        img_src = None
        try:
            # First, try to get the image from the <source> tag inside <picture>
            source_elem = container.find_element(By.CSS_SELECTOR, "div.image picture source")
            candidate = source_elem.get_attribute("srcset")
            if "Media/PreloadImages" in candidate:
                raise Exception("Preload image found, switching to <img>")
            else:
                img_src = candidate
        except Exception:
            try:
                # Fallback: get the image from the <img> tag
                img_elem = container.find_element(By.CSS_SELECTOR, "div.image img")
                # Wait until the src attribute does not contain the preload path
                WebDriverWait(driver, 10).until(
                    lambda d: "Media/PreloadImages" not in img_elem.get_attribute("src")
                )
                candidate = img_elem.get_attribute("src")
                if "Media/PreloadImages" in candidate:
                    img_src = "N/A"
                else:
                    img_src = candidate
            except Exception as e:
                print("Error extracting image:", e)
                img_src = "N/A"
        
        # Convert relative URL to absolute if necessary.
        if img_src != "N/A" and not img_src.startswith("http"):
            img_src = "https://www.zer4u.co.il/" + img_src.lstrip("/")

        # --- Extract the description from the <h2> with data-equalheight="prodTitle" ---
        try:
            desc_elem = container.find_element(By.CSS_SELECTOR, "h2[data-equalheight='prodTitle']")
            description = desc_elem.text.strip()
        except Exception as e:
            print("Error extracting description:", e)
            description = "N/A"

        # --- Extract the price from the <span class="saleprice"> ---
        try:
            price_elem = container.find_element(By.CSS_SELECTOR, "span.saleprice")
            price = price_elem.text.strip()
        except Exception as e:
            print("Error extracting price:", e)
            price = "N/A"

        # --- Insert the Data into the SQLite Database ---
        cursor.execute(
            "INSERT INTO products (description, price, img_url, page) VALUES (?, ?, ?, ?)",
            (description, price, img_src, page)
        )
        conn.commit()
        print(f"Inserted: {description} | {price} | {img_src}")

    page += 1

driver.quit()
conn.close()
print("Scraping complete!")
