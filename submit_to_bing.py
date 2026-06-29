"""
submit_to_bing.py

Checks the sitemap.xml of claritywithai.org for URLs, compares against a
list of URLs already submitted (stored in bing-seen-urls.json in this
repo), and submits any new ones to the Bing Webmaster API so Bing crawls
them right away instead of waiting for its normal crawl schedule.

Run inside GitHub Actions via the submit-to-bing.yml workflow.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
import requests

SITEMAP_URL = os.environ.get("SITEMAP_URL", "https://www.claritywithai.org/sitemap.xml")
SITE_URL = os.environ.get("SITE_URL", "https://www.claritywithai.org")
BING_API_KEY = os.environ.get("BING_API_KEY", "")
SEEN_URLS_FILE = os.environ.get("SEEN_URLS_FILE", "bing-seen-urls.json")
BING_ENDPOINT = "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch"

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


def submit_to_bing(urls: list[str]) -> bool:
    if not BING_API_KEY:
        print("Error: BING_API_KEY is not set.")
        return False

    endpoint = f"{BING_ENDPOINT}?apikey={BING_API_KEY}"
    payload = {
        "siteUrl": SITE_URL,
        "urlList": urls,
    }

    resp = requests.post(
        endpoint,
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )

    print(f"Bing API response: {resp.status_code}")
    if resp.text:
        print(resp.text)

    # Bing returns 200 with no body (or null) on success
    return resp.status_code == 200


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
        print("No new URLs found. Nothing to submit to Bing.")
        return

    # Bing allows up to 10,000 URLs per batch submission; chunk just in case.
    print(f"Found {len(new_urls)} new URL(s). Submitting to Bing...")
    for url in new_urls:
        print(f"  + {url}")

    success = submit_to_bing(new_urls)

    if success:
        seen_urls.update(new_urls)
        save_seen_urls(SEEN_URLS_FILE, seen_urls)
        print("Successfully submitted and updated seen-urls record.")
    else:
        print("Submission failed — not updating seen-urls record, will retry next run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
