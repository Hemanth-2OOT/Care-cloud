import sys
import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Logging in...")
        try:
            page.goto("http://localhost:5000/login")
            page.fill("input[name='email']", "test@logic.com")
            page.fill("input[name='password']", "password")
            page.click("button[type='submit']")
            page.wait_for_url("**/dashboard", timeout=5000)
        except Exception as e:
            print(f"Login failed: {e}")
            sys.exit(1)

        # Test 1: Self Harm Context
        print("Testing Self Harm Context...")
        page.fill("#text_content", "I want to kill myself")
        page.click("#analyzeBtn")
        page.wait_for_selector("#resultsContent", state="visible", timeout=5000)
        time.sleep(1)

        labels = page.text_content("#labelsContainer")
        print(f"Labels for 'kill myself': {labels.strip()}")
        if "Self-Harm Risk" not in labels:
            print("ERROR: Expected 'Self-Harm Risk' label.")
            sys.exit(1)

        print("Logic Verification successful.")
        browser.close()

if __name__ == "__main__":
    run()
