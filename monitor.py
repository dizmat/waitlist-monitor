import hashlib, time, requests, os, schedule
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

URLS = [
    "https://www.unsw.edu.au/science/psychology-clinic/waitlists",
    "https://www.unsw.edu.au/science/neuropsychology-clinic/waitlists",
]

KEYWORDS = ["neuropsychological", "neuropsych", "adult neuropsych"]
SNAPSHOT_FILE = "snapshots.txt"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; waitlist-monitor/1.0)"}

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    )

def extract_relevant_text(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Find any element containing neuropsych keywords
    results = []
    for tag in soup.find_all(string=True):
        if any(kw in tag.lower() for kw in KEYWORDS):
            parent = tag.parent
            results.append(parent.get_text(strip=True))

    return "\n".join(results) if results else soup.get_text()

def load_snapshots():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    lines = open(SNAPSHOT_FILE).read().strip().split("\n")
    snaps = {}
    for line in lines:
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
                msg = (
                    f"🔔 <b>Waitlist change detected!</b>\n\n"
                    f"The neuropsychological assessment waitlist section may have changed.\n\n"
                    f"<a href='{url}'>Check it now →</a>"
                )
                send_message(msg)
                print(f"Change detected at {url} — notification sent.")
            else:
                print(f"No change at {url}")

        except Exception as e:
            print(f"Error checking {url}: {e}")

    save_snapshots(snaps)

# Run once immediately, then once per day
check()
send_message("✅ Bot is live and monitoring the UNSW waitlist. You'll be notified when the neuropsychological assessment waitlist changes.")
schedule.every().day.at("09:00").do(check)

while True:
    schedule.run_pending()
    time.sleep(60)
