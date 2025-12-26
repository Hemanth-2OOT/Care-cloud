import time
from playwright.sync_api import sync_playwright, expect

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Login
        page.goto("http://127.0.0.1:5000/login")
        page.fill("input[name='email']", "child@test.com")
        page.fill("input[name='password']", "password")
        page.click("button[type='submit']")

        # Wait for dashboard
        page.wait_for_url("**/dashboard")

        # 2. Analyze Text (Force Fallback)
        # Using correct selector from dashboard.html: id="text_content"
        page.fill("#text_content", "I hate you so much")
        page.click("button#analyzeBtn")

        # Wait for results
        # The #resultsContent is hidden by default?
        # Actually script.js likely toggles visibility.
        # Let's wait for #riskScore to be visible which is inside #resultsContent
        page.wait_for_selector("#riskScore", state="visible")
        time.sleep(2) # Allow transitions

        # 3. Verify Elements
        # Check if score is visible and labels are present
        expect(page.locator("#riskScore")).to_be_visible()
        # The .label-badge class is likely created by script.js
        # Let's verify we have at least one child in labelsContainer
        # Labels for "hate": Harassment, Emotional Abuse -> 2 labels
        expect(page.locator("#labelsContainer > span")).to_have_count(2)

        # 4. Screenshot
        page.screenshot(path="verification/dashboard_analysis.png", full_page=True)
        print("Screenshot saved to verification/dashboard_analysis.png")

        browser.close()

if __name__ == "__main__":
    run()
