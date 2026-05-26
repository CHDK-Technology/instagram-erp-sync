import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# INSTAGRAM CONFIG
INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# ERPNEXT CONFIG
ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# FETCH INSTAGRAM DATA
url = f"https://graph.facebook.com/v25.0/{INSTAGRAM_ID}"

params = {
    "fields": "username,followers_count,media_count",
    "access_token": ACCESS_TOKEN
}

response = requests.get(url, params=params)
instagram_data = response.json()

print("Instagram Data:")
print(instagram_data)

headers = {
    "Authorization": f"token {API_KEY}:{API_SECRET}"
}

# CHECK EXISTING RECORD
check_response = requests.get(
    f"{ERP_URL}/api/resource/Instagram Analytics",
    headers=headers
)

records = check_response.json().get("data", [])

payload = {
    "instagram_username": instagram_data.get("username"),
    "followers_count": instagram_data.get("followers_count"),
    "media_count": instagram_data.get("media_count"),
    "last_sync": str(datetime.now())
}

# UPDATE EXISTING RECORD
if records:
    record_name = records[0]["name"]

    update_response = requests.put(
        f"{ERP_URL}/api/resource/Instagram Analytics/{record_name}",
        json=payload,
        headers=headers
    )

    print("\nUpdated Existing Record:")
    print(update_response.json())

# CREATE NEW RECORD
else:
    payload["doctype"] = "Instagram Analytics"

    create_response = requests.post(
        f"{ERP_URL}/api/resource/Instagram Analytics",
        json=payload,
        headers=headers
    )

    print("\nCreated New Record:")
    print(create_response.json())