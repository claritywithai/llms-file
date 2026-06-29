"""
check_new_posts.py

Fetches the sitemap.xml of claritywithai.org, compares the URLs against
what's already listed in llms.txt, and appends any new post URLs
(with an auto-generated title line) to llms.txt.

Designed to run inside the GitHub Actions workflow `update-llms.yml`,
but can also be run locally:

    pip install requests
    python check_new_posts.py
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
import requests

SITEMAP_URL = os.environ.get("SITEMAP_URL", "https://claritywithai.org/sitemap.xml")
LLMS_FILE = os.environ.get("LLMS_FILE", "llms.txt")

NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    """Download and parse a sitemap.xml, returning all <loc> URLs.
    Handles sitemap index files (sitemaps of sitemaps) by recursing one level.
    """
    resp = requests.get(sitemap_url, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    urls = []

    # Case 1: this is a sitemap index pointing to other sitemaps
    sitemap_entries = root.findall("sm:sitemap/sm:loc", NAMESPACE)
    if sitemap_entries:
        for entry in sitemap_entries:
            sub_url = entry.text.strip()
            try:
                urls.extend(fetch_sitemap_urls(sub_url))
            except requests.RequestException as e:
                print(f"Warning: could not fetch sub-sitemap {sub_url}: {e}")
        return urls

    # Case 2: this is a regular urlset
    url_entries = root.findall("sm:url/sm:loc", NAMESPACE)
    for entry in url_entries:
        urls.append(entry.text.strip())

    return urls


def load_existing_urls(llms_path: str) -> set[str]:
    """Read llms.txt and return the set of URLs already listed in it."""
    if not os.path.exists(llms_path):
        return set()

    with open(llms_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Grab any http(s) URL already present in the file
    return set(re.findall(r"https?://[^\s\)\]]+", content))


def slug_to_title(url: str) -> str:
    """Turn a URL slug into a human-readable title fallback,
    e.g. https://site.org/2026/06/my-cool-post.html -> 'My Cool Post'
    """
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.html?$", "", slug)
    slug = slug.replace("-", " ").replace("_", " ").strip()
    return slug.title() if slug else url


def main():
    print(f"Fetching sitemap: {SITEMAP_URL}")
    try:
        sitemap_urls = fetch_sitemap_urls(SITEMAP_URL)
    except requests.RequestException as e:
        print(f"Error fetching sitemap: {e}")
        sys.exit(1)

    # Only keep actual post pages — adjust this filter to match your URL pattern.
    # Example: skip homepage, tag pages, search pages, etc.
    post_urls = [
        u for u in sitemap_urls
        if "/search" not in u and "/label/" not in u and u.rstrip("/").count("/") > 2
    ]

    existing_urls = load_existing_urls(LLMS_FILE)
    new_urls = [u for u in post_urls if u not in existing_urls]

    if not new_urls:
        print("No new posts found. llms.txt is already up to date.")
        return

    print(f"Found {len(new_urls)} new post(s). Appending to {LLMS_FILE}...")

    lines_to_add = []
    for url in new_urls:
        title = slug_to_title(url)
        lines_to_add.append(f"- [{title}]({url})")

    with open(LLMS_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines_to_add) + "\n")

    for url in new_urls:
        print(f"  + {url}")


if __name__ == "__main__":
    main()
