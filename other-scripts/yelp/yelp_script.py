import requests
import json
import time
from datetime import datetime

# ==============================
#  CONFIGURATION
# ==============================

API_KEY = "YELP_API_KEY"   # 
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

CUISINES = ["indian", "italian", "chinese", "mexican", "japanese"]
LOCATION = "Manhattan"
LIMIT = 50
TARGET_PER_CUISINE = 200
PAUSE_SECONDS = 1

# ==============================
#  MAIN SCRIPT
# ==============================

all_data = []

for cuisine in CUISINES:
    print(f"\n🍴 Fetching {cuisine.title()} restaurants in {LOCATION} ...")
    results = []
    offset = 0

    while len(results) < TARGET_PER_CUISINE:
        url = "https://api.yelp.com/v3/businesses/search"
        params = {"term": cuisine, "location": LOCATION, "limit": LIMIT, "offset": offset}

        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ Yelp API error {response.status_code}: {response.text}")
                break

            data = response.json().get("businesses", [])
            if not data:
                print("⚠️ No more businesses returned, ending early.")
                break

            for b in data:
                loc = b.get("location", {})
                coords = b.get("coordinates", {})

                # Skip incomplete entries
                if not loc.get("display_address") or not b.get("name"):
                    continue

                entry = {
                    "business_id": b.get("id", ""),
                    "name": b.get("name", "").strip(),
                    "display_address": ", ".join(loc.get("display_address", [])),
                    "coordinates": {
                        "latitude": coords.get("latitude"),
                        "longitude": coords.get("longitude")
                    },
                    "review_count": b.get("review_count", 0),
                    "rating": b.get("rating", 0),
                    "zip_code": loc.get("zip_code", ""),
                    "insertedAtTimestamp": datetime.utcnow().isoformat() + "Z",
                    "Cuisine": cuisine
                }

                results.append(entry)

                # Show progress every 20
                if len(results) % 20 == 0:
                    print(f"   → {len(results)} collected so far for {cuisine}")

            offset += LIMIT
            time.sleep(PAUSE_SECONDS)

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            break

    results = results[:TARGET_PER_CUISINE]
    all_data.extend(results)
    print(f"✅ Done: {len(results)} valid {cuisine} restaurants collected.\n")

# ==============================
#  CLEANUP + VALIDATION
# ==============================

clean_data = [
    r for r in all_data
    if r["Cuisine"] and r["name"] and r["display_address"]
]

total = len(clean_data)
print(f"\n🧹 After cleaning: {total} complete restaurant records remain.")
print(f"   ≈ {total // len(CUISINES)} per cuisine on average.\n")

# ==============================
#  SAVE FILES
# ==============================

output_json = "final_yelp_restaurants.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(clean_data, f, indent=2, ensure_ascii=False)
print(f"💾 JSON saved: {output_json}")

# Optional CSV
import csv
output_csv = "final_yelp_restaurants.csv"
with open(output_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "Cuisine", "business_id", "name", "rating", "review_count",
            "zip_code", "display_address", "coordinates", "insertedAtTimestamp"
        ]
    )
    writer.writeheader()
    writer.writerows(clean_data)
print(f"📊 CSV saved: {output_csv}")

print("\n🎉 All done! Data ready for DynamoDB upload.")
