import os
import time
import csv
import random
from datetime import datetime
import pytz
import schedule  # Scheduler library
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth  # For stealth mode

# --- Configuration ---
USERNAME = "info@rutlandvapes.com"  # Replace with your username
PASSWORD = "Tundra2008"            # Replace with your password

# List your CSV files (each with up to 500 SKUs)
CSV_FILES = ["sku1.csv", "sku2.csv", "sku3.csv", "sku4.csv", "sku5.csv", "sku6.csv", "sku7.csv", "sku8.csv", "sku9.csv", "sku10.csv", "sku11.csv", "sku12.csv"]

# CSS selectors / locators
LOGIN_EMAIL_SELECTOR = "input#email"      # Update if necessary
LOGIN_PASSWORD_SELECTOR = "input#pass"      # Update if necessary
LOGIN_BUTTON_SELECTOR = "button.login"      # Update if necessary

UPLOAD_BUTTON_SELECTOR = ".custom-file-upload"  # The file upload button (if needed)
FILE_INPUT_ID = "customer_sku_csv"              # File input element on quick order page

VERIFICATION_POPUP_SELECTOR = "a.popup-button.enter-button"  # Verification popup (pre-login)

# Selector for product rows (ignoring header row with extra class "deletable-item-title")
PRODUCT_ROW_SELECTOR = "fieldset[data-container='items'] > div.fields.additional.deletable-item:not(.deletable-item-title)"


def run_job(csv_file):
    """
    Processes the given CSV file by:
      1. Randomizing the Qty field (assumed to be in column index 1) for each row to a random integer between 950 and 1050.
      2. Uploading the randomized CSV file.
      3. Scraping product rows from the website.
      4. Comparing scraped SKUs with those in the CSV.
         For any SKU missing on the website, outputs a record with empty Product Name and Price, and Qty=0.
      5. Returns a list of rows [SKU Number, Product Name, Price, Qty, Date].
    """
    # Get current Eastern Time with hours and minutes.
    eastern = pytz.timezone("US/Eastern")
    now_est = datetime.now(eastern)
    run_date = now_est.strftime('%Y-%m-%d_%H-%M')
    part = "Part-1" if now_est.hour < 12 else "Part-2"
    print(f"\nJob started for {csv_file}. (Timestamp: {run_date}, {part})")
    
    # --- Pre-process: Randomize Qty in the CSV file ---
    randomized_csv_file = csv_file.replace(".csv", "_randomized.csv")
    with open(csv_file, newline='', encoding='utf-8') as infile, open(randomized_csv_file, 'w', newline='', encoding='utf-8') as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        header = next(reader)
        writer.writerow(header)
        for row in reader:
            if len(row) > 1:
                row[1] = str(random.randint(950, 1050))
            writer.writerow(row)
    print(f"Created randomized CSV file: {randomized_csv_file}")
    
    # Setup Selenium with Chrome.
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
    
    # --- Implement stealth technique ---
    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="MacIntel",
            webgl_vendor="Apple Inc.",
            renderer="Apple GPU",
            fix_hairline=True,
    )
    
    extracted_data = []  # Will store rows: [SKU Number, Product Name, Price, Qty, Date]
    scraped_skus = set()
    
    try:
        driver.maximize_window()
        
        # --- Step 1: Navigate to the login page ---
        driver.get("http://pacificsmoke.com/en/customer/account/login")
        
        # --- Step 2: Handle the verification popup ---
        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, VERIFICATION_POPUP_SELECTOR))
            )
            driver.find_element(By.CSS_SELECTOR, VERIFICATION_POPUP_SELECTOR).click()
            time.sleep(2)
        except Exception as e:
            print("Verification popup not found or not clickable; continuing...")
        
        # --- Step 3: Log in ---
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, LOGIN_EMAIL_SELECTOR))
        )
        driver.find_element(By.CSS_SELECTOR, LOGIN_EMAIL_SELECTOR).send_keys(USERNAME)
        time.sleep(1)
        driver.find_element(By.CSS_SELECTOR, LOGIN_PASSWORD_SELECTOR).send_keys(PASSWORD)
        time.sleep(1)
        driver.find_element(By.CSS_SELECTOR, LOGIN_BUTTON_SELECTOR).click()
        time.sleep(3)
        
        # --- Step 4: Navigate to the quick order page ---
        driver.get("https://www.pacificsmoke.com/en/quickorder/")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, FILE_INPUT_ID))
        )
        
        # --- Step 5: Upload the randomized CSV file ---
        sku_file_path = os.path.join(os.getcwd(), randomized_csv_file)
        file_input = driver.find_element(By.ID, FILE_INPUT_ID)
        driver.execute_script(
            "arguments[0].removeAttribute('style');"
            "arguments[0].style.display = 'block';"
            "arguments[0].style.visibility = 'visible';", 
            file_input
        )
        file_input.send_keys(sku_file_path)
        time.sleep(30)
        
        # --- Step 6: Scrape product rows with retry mechanism ---
        max_retries = 3
        product_rows = []
        for attempt in range(max_retries):
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, PRODUCT_ROW_SELECTOR))
                )
                product_rows = driver.find_elements(By.CSS_SELECTOR, PRODUCT_ROW_SELECTOR)
                if product_rows:
                    product_rows = product_rows[:-1]
                if product_rows and len(product_rows) > 0:
                    print(f"Attempt {attempt+1}: Found {len(product_rows)} valid product rows.")
                    break
                else:
                    print(f"Attempt {attempt+1}: No product rows found. Retrying...")
            except Exception as e:
                print(f"Attempt {attempt+1}: Error while waiting for product rows: {e}")
            if attempt < max_retries - 1:
                driver.refresh()
                time.sleep(15)
        if not product_rows:
            print("Product rows still not loaded after retries.")
            return []
        
        for idx, row in enumerate(product_rows):
            try:
                product_name = row.find_element(By.CSS_SELECTOR, "p.item-name strong").text.strip()
            except Exception as e:
                product_name = ""
            try:
                sku_text = row.find_element(By.CSS_SELECTOR, "p.item-sku").text.strip()
                sku_number = sku_text.replace("SKU:", "").strip()
            except Exception as e:
                sku_number = ""
            try:
                price = row.find_element(By.CSS_SELECTOR, "p.price").text.strip()
            except Exception as e:
                price = ""
            try:
                qty_input = row.find_element(By.CSS_SELECTOR, "input[data-role='product-qty']")
                qty_value = qty_input.get_attribute("value").strip()
            except Exception as e:
                qty_value = ""
            
            extracted_data.append([sku_number, product_name, price, qty_value, run_date])
            scraped_skus.add(sku_number)
            print(f"Row {idx}: Product Name='{product_name}', SKU='{sku_number}', Price='{price}', Qty='{qty_value}'")
        
        # --- Step 7: Read expected SKUs from the randomized CSV file ---
        expected_skus = []
        with open(randomized_csv_file, newline='', encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)
            for row in reader:
                if row:
                    expected_skus.append(row[0].strip())
        
        # --- Step 8: For any expected SKU not scraped, add a record with empty Product Name, empty Price, and Qty=0 ---
        for sku in expected_skus:
            if sku not in scraped_skus:
                extracted_data.append([sku, "", "", "0", run_date])
                print(f"SKU '{sku}' not found on page; added with empty Product Name, empty Price, and Qty=0.")
        
    except Exception as ex:
        print("An error occurred during the job:", ex)
    
    finally:
        driver.quit()
    
    return extracted_data

def main_job():
    """
    Processes all CSV files and writes the combined extracted data to a single output CSV file.
    """
    all_extracted_data = []
    eastern = pytz.timezone("US/Eastern")
    now_est = datetime.now(eastern)
    run_date = now_est.strftime('%Y-%m-%d_%H-%M')
    part = "Part-1" if now_est.hour < 12 else "Part-2"
    for csv_file in CSV_FILES:
        data = run_job(csv_file)
        all_extracted_data.extend(data)
    combined_output_file = f"{run_date}-{part}-combined.csv"
    with open(combined_output_file, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["SKU Number", "Product Name", "Price", "Qty", "Date"])
        writer.writerows(all_extracted_data)
    print(f"\nCombined data extraction complete. {len(all_extracted_data)} records saved to {combined_output_file}.")

def main_job_wrapper():
    """
    Waits for a random delay (up to 3600 seconds) before running the main job.
    This random delay makes the effective run time fall randomly within the scheduled window.
    """
    delay = random.uniform(0, 3600)
    print(f"Job triggered. Sleeping for {delay:.0f} seconds before execution...")
    time.sleep(delay)
    main_job()

# --- Scheduler: run the job every morning between 8AM-9AM and every afternoon between 5PM-6PM ---
schedule.every().day.at("08:00").do(main_job_wrapper)
schedule.every().day.at("17:00").do(main_job_wrapper)

print("Scheduler started. Waiting for scheduled jobs...")
while True:
    schedule.run_pending()
    time.sleep(1)
