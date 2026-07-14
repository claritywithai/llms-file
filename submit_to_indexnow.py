"""
submit_to_indexnow.py

Checks the sitemap.xml of claritywithai.org for URLs, compares against a
list of URLs already submitted (stored in indexnow-seen-urls.json in this
repo), and submits any new ones to the IndexNow API so Bing, Yandex, and
other participating search engines crawl them immediately instead of
waiting for their normal crawl schedule.

Run inside GitHub Actions via the submit-to-indexnow.yml workflow.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
import requests

SITEMAP_URL = os.environ.get("SITEMAP_URL", "https://claritywithai.org/sitemap.xml")
HOST = os.environ.get("HOST", "www.claritywithai.org")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")
KEY_LOCATION = os.environ.get(
    "KEY_LOCATION", f"https://files.claritywithai.org/{INDEXNOW_KEY}.txt"
)
SEEN_URLS_FILE = os.environ.get("SEEN_URLS_FILE", "indexnow-seen-urls.json")
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    resp = requests.get(sitemap_url, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    urls = []
    sitemap_entries = root.findall("sm:sitemap/sm:loc", NAMESPACE)
    if sitemap_entries:
        for entry in sitemap_entries:
            sub_url = entry.text.strip()
            try:
                urls.extend(fetch_sitemap_urls(sub_url))
            except requests.RequestException as e:
                print(f"Warning: could not fetch sub-sitemap {sub_url}: {e}")
        return urls

    url_entries = root.findall("sm:url/sm:loc", NAMESPACE)
    for entry in url_entries:
        urls.append(entry.text.strip())
    return urls


def load_seen_urls(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        try:
            return set(json.load(f))
        except json.JSONDecodeError:
            return set()


def save_seen_urls(path: str, urls: set[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(urls), f, indent=2)


def submit_to_indexnow(urls: list[str]) -> bool:
    if not INDEXNOW_KEY:
        print("Error: INDEXNOW_KEY is not set.")
        return False

    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }

    resp = requests.post(
        INDEXNOW_ENDPOINT,
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )

    print(f"IndexNow response: {resp.status_code}")
    if resp.text:
        print(resp.text)

    # IndexNow returns 200 or 202 on success
    return resp.status_code in (200, 202)


def main():
    print(f"Fetching sitemap: {SITEMAP_URL}")
    try:
        all_urls = set(fetch_sitemap_urls(SITEMAP_URL))
    except requests.RequestException as e:
        print(f"Error fetching sitemap: {e}")
        sys.exit(1)

    seen_urls = load_seen_urls(SEEN_URLS_FILE)
    new_urls = list(all_urls - seen_urls)

    if not new_urls:
        print("No new URLs found. Nothing to submit to IndexNow.")
        return

    print(f"Found {len(new_urls)} new URL(s). Submitting to IndexNow...")
    for url in new_urls:
        print(f"  + {url}")

    success = submit_to_indexnow(new_urls)

    if success:
        seen_urls.update(new_urls)
        save_seen_urls(SEEN_URLS_FILE, seen_urls)
        print("Successfully submitted and updated seen-urls record.")
    else:
        print("Submission failed — not updating seen-urls record, will retry next run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
