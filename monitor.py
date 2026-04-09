import hashlib, os, schedule, time, requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

URLS = [
    "https://www.unsw.edu.au/science/psychology-clinic/waitlists",
    "https://www.unsw.edu.au/science/neuropsychology-clinic/waitlists",
    "https://www.sydney.edu.au/brain-mind/our-clinics/psychology-clinic.html",
]

KEYWORDS = ["neuropsychological", "neuropsych", "adult neuropsych", "psychometric"]
SNAPSHOT_FILE = "snapshots.txt"

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    )

def send_photo(photo_path, caption=""):
    with open(photo_path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": f}
        )

def extract_relevant_text(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        content = page.inner_text("body")
        browser.close()

    lines = content.splitlines()
    results = [l.strip() for l in lines if any(kw in l.lower() for kw in KEYWORDS)]

    print(f"--- SCRAPE RESULT: {url} ---")
    if results:
        print(f"Keywords found ({len(results)} line(s)):")
        for line in results:
            print(f"  >> {line}")
    else:
        print("No keywords found. Falling back to first 500 chars of page:")
        print(content[:500])
    print("--- END ---")

    return "\n".join(results) if results else content[:500]

def dismiss_cookies(page):
    """Try to dismiss cookie popups on UNSW and USyd sites."""
    cookie_buttons = [
        "text=Accept only essential",
        "text=Accept all",
        "button:has-text('Accept')",
        "[aria-label='Close']",
    ]
    for selector in cookie_buttons:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(500)
                return
        except Exception:
            continue

def take_screenshot(url):
    """Take a screenshot of the waitlist status area on each page."""
    screenshot_path = f"/tmp/screenshot_{hashlib.md5(url.encode()).hexdigest()}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=30000)

        dismiss_cookies(page)

        # UNSW pages: click the "Adult Neuropsychological Assessments" tab
        if "unsw.edu.au" in url:
            try:
                tab = page.locator("text=Adult Neuropsychological Assessments").first
                if tab.is_visible(timeout=3000):
                    tab.click()
                    page.wait_for_timeout(1000)
                    tab.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    # Scroll down a bit more to get past the hero image
                    page.evaluate("window.scrollBy(0, 300)")
                    page.wait_for_timeout(300)
            except Exception:
                print(f"Could not click neuropsych tab on {url}")

        # USyd page: scroll to the waitlist status section
        if "sydney.edu.au" in url:
            try:
                loc = page.locator("text=/waitlist/i").first
                if loc.is_visible(timeout=3000):
                    loc.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
            except Exception:
                print(f"Could not scroll to waitlist section on {url}")

        page.screenshot(path=screenshot_path)
        browser.close()

    return screenshot_path

def load_snapshots():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    snaps = {}
    for line in open(SNAPSHOT_FILE).read().strip().split("\n"):
        if "|" in line:
            url, h = line.split("|", 1)
            snaps[url] = h
    return snaps

def save_snapshots(snaps):
    with open(SNAPSHOT_FILE, "w") as f:
        for url, h in snaps.items():
            f.write(f"{url}|{h}\n")

def check():
    print("Running check...")
    snaps = load_snapshots()
    for url in URLS:
        try:
            text = extract_relevant_text(url)
            current_hash = hashlib.md5(text.encode()).hexdigest()
            previous_hash = snaps.get(url)

            if previous_hash is None:
                snaps[url] = current_hash
                print(f"Initial snapshot saved for {url}")
            elif current_hash != previous_hash:
                snaps[url] = current_hash
                send_message(
                    f"🔔 <b>Waitlist change detected!</b>\n\n"
                    f"<a href='{url}'>Check it now →</a>"
                )
                print(f"Change detected — notification sent.")
            else:
                print(f"No change at {url}")
        except Exception as e:
            print(f"Error checking {url}: {e}")
    save_snapshots(snaps)

def send_daily_screenshots():
    print("Sending daily screenshots...")
    for url in URLS:
        try:
            path = take_screenshot(url)
            send_photo(path, caption=f"📸 Daily snapshot\n{url}")
            os.remove(path)
            print(f"Screenshot sent for {url}")
        except Exception as e:
            print(f"Error screenshotting {url}: {e}")

check()
send_daily_screenshots()
send_message("✅ Bot restarted and monitoring UNSW + USyd waitlists.")
schedule.every().day.at("09:00").do(check)
schedule.every().day.at("09:01").do(send_daily_screenshots)

while True:
    schedule.run_pending()
    time.sleep(60)
