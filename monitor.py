import hashlib, os, schedule, time, requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

URLS = [
    "https://www.unsw.edu.au/science/psychology-clinic/waitlists",
    "https://www.unsw.edu.au/science/neuropsychology-clinic/waitlists",
]

KEYWORDS = ["neuropsychological", "neuropsych", "adult neuropsych"]
SNAPSHOT_FILE = "snapshots.txt"

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
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

check()
send_message("✅ Bot restarted and monitoring UNSW waitlists.")
schedule.every().day.at("09:00").do(check)

while True:
    schedule.run_pending()
    time.sleep(60)
