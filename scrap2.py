import time
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

# --- Setup SQLite Database ---
conn = sqlite3.connect('zer4u_products2.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT,
    price TEXT,
    img_url TEXT
)
''')
conn.commit()

# --- Setup Selenium WebDriver ---
service = Service()  # Optionally, specify the path to chromedriver if needed
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Run headless
driver = webdriver.Chrome(service=service, options=options)

# --- Load the Category Page (Page 2) ---
category_url = "https://www.zer4u.co.il/%D7%96%D7%A8%D7%99_%D7%A4%D7%A8%D7%97%D7%99%D7%9D?bscrp=2"
driver.get(category_url)
time.sleep(3)  # Wait for the page to fully load

# --- Find All Product Containers ---
product_containers = driver.find_elements(By.CSS_SELECTOR, "div.product_in_list")
print(f"Found {len(product_containers)} products on the page.")

# --- Loop Through Each Container and Extract Data ---
for container in product_containers:
    # --- Extract the image URL ---
    try:
        # Try to get the image from the <source> tag inside <picture>
        img_elem = container.find_element(By.CSS_SELECTOR, "div.image picture source")
        img_src = img_elem.get_attribute("srcset")
    except Exception as e:
        try:
            # Fallback: get the image from the <img> tag if <source> is not available
            img_elem = container.find_element(By.CSS_SELECTOR, "div.image img")
            img_src = img_elem.get_attribute("src")
        except Exception as e:
            print("Error extracting image:", e)
            img_src = "N/A"
    
    # Convert relative URL to absolute if necessary
    if not img_src.startswith("http"):
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
    cursor.execute("INSERT INTO products (description, price, img_url) VALUES (?, ?, ?)",
                   (description, price, img_src))
    conn.commit()
    print(f"Inserted product: {description} | {price} | {img_src}")

driver.quit()
conn.close()
print("Scraping complete!")
