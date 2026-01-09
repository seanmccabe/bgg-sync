import requests
import xml.etree.ElementTree as ET

API_TOKEN = "e14bf54c-d47e-47ea-8b48-4505e64785fe"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"Bearer {API_TOKEN}"
}

# 1. Check Collection API
print("--- Checking Collection API ---")
COLL_URL = "https://boardgamegeek.com/xmlapi2/collection?username=seanmccabe&limit=1&stats=1&subtype=boardgame"
resp = requests.get(COLL_URL, headers=headers)
if resp.status_code == 200:
    root = ET.fromstring(resp.content)
    item = root.find("item")
    if item:
        print(f"Game: {item.findtext('name')}")
        print(f"Image: {item.findtext('image')}")
        print(f"Thumbnail: {item.findtext('thumbnail')}")
    else:
        print("No items in collection.")
else:
    print(f"Collection API Failed: {resp.status_code}")

# 2. Check Thing API
print("\n--- Checking Thing API (ID 822) ---")
THING_URL = "https://boardgamegeek.com/xmlapi2/thing?id=822&stats=1"
resp = requests.get(THING_URL, headers=headers)
if resp.status_code == 200:
    root = ET.fromstring(resp.content)
    item = root.find("item")
    if item:
        print(f"Game: {item.find('name').get('value')}")
        print(f"Image: {item.findtext('image')}")
        print(f"Thumbnail: {item.findtext('thumbnail')}")
    else:
        print("No item found.")
else:
    print(f"Thing API Failed: {resp.status_code}")
