import time
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

# --- Setup SQLite Database ---
conn = sqlite3.connect('zer4u_products.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price TEXT,
    img_url TEXT
)
''')
conn.commit()

# --- Setup Selenium WebDriver ---
service = Service()  # Optionally, specify path: Service('/path/to/chromedriver')
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Run without opening a browser window
driver = webdriver.Chrome(service=service, options=options)

# --- Load the Category Page (Page 2) ---
category_url = "https://www.zer4u.co.il/%D7%96%D7%A8%D7%99_%D7%A4%D7%A8%D7%97%D7%99%D7%9D?bscrp=2"
driver.get(category_url)
time.sleep(3)  # Allow time for the page to load

# --- Extract Unique Product Links ---
product_links = set()
product_containers = driver.find_elements(By.CSS_SELECTOR, "div.product_in_list")
for container in product_containers:
    try:
        a_tag = container.find_element(By.TAG_NAME, "a")
        product_url = a_tag.get_attribute("href")
        if product_url:
            # Convert relative URLs to absolute if needed
            if not product_url.startswith("http"):
                product_url = "https://www.zer4u.co.il" + product_url
            product_links.add(product_url)
    except Exception as e:
        print("Error finding link in container:", e)

product_links = list(product_links)
print("Found product links:", product_links)

# --- Loop Through Each Product Link ---
for product_url in product_links:
    driver.get(product_url)
    time.sleep(2)  # Wait for the product page to load

    try:
        # Extract product name and price
        name_elem = driver.find_element(By.CSS_SELECTOR, "span.ptitle")
        price_elem = driver.find_element(By.CSS_SELECTOR, "span.saleprice")
        name = name_elem.text.strip() if name_elem else "N/A"
        price = price_elem.text.strip() if price_elem else "N/A"

        # Extract image URL from the <source> tag within <picture>
        try:
            source_elem = driver.find_element(By.CSS_SELECTOR, "picture source[type='image/webp']")
            img_src = source_elem.get_attribute("srcset")
        except Exception:
            # Fallback to the <img> tag if <source> is not found
            img_elem = driver.find_element(By.CSS_SELECTOR, "img.img-responsive.center-block")
            img_src = img_elem.get_attribute("src")
        
        # Convert relative path to absolute URL if needed
        if not img_src.startswith("http"):
            img_src = "https://www.zer4u.co.il/" + img_src.lstrip("/")
        
        # Insert the extracted data into the SQLite database
        cursor.execute('INSERT INTO products (name, price, img_url) VALUES (?, ?, ?)',
                       (name, price, img_src))
        conn.commit()
        
        print(f"Inserted product: {name}")
    except Exception as e:
        print(f"Error processing {product_url}: {e}")
        continue

driver.quit()
conn.close()
print("Scraping complete!")
