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

# --- VALIDATE CONFIG ---
missing = [k for k, v in {
    "INSTAGRAM_ID": INSTAGRAM_ID,
    "ACCESS_TOKEN": ACCESS_TOKEN,
    "ERP_URL": ERP_URL,
    "API_KEY": API_KEY,
    "API_SECRET": API_SECRET
}.items() if not v]

if missing:
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

# --- FETCH INSTAGRAM DATA ---
url = f"https://graph.facebook.com/v25.0/{INSTAGRAM_ID}"

params = {
    "fields": "username,followers_count,media_count",
    "access_token": ACCESS_TOKEN
}

response = requests.get(url, params=params)
instagram_data = response.json()

print("Instagram Data:", instagram_data)

# FIX: Check for Meta API error before proceeding
if instagram_data.get("error"):
    print("META API ERROR:", instagram_data["error"])
    exit(1)

headers = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json"
}

# --- CHECK EXISTING RECORD ---
check_response = requests.get(
    f"{ERP_URL}/api/resource/Instagram Analytics",
    headers=headers
)

print("ERPNext check status:", check_response.status_code)

if check_response.status_code != 200:
    print("ERPNext check failed:", check_response.text)
    exit(1)

records = check_response.json().get("data", [])

payload = {
    "instagram_username": instagram_data.get("username"),
    "followers_count": instagram_data.get("followers_count"),
    "media_count": instagram_data.get("media_count"),
    "last_sync": str(datetime.now())
}

# --- UPDATE OR CREATE ---
if records:
    record_name = records[0]["name"]

    update_response = requests.put(
        f"{ERP_URL}/api/resource/Instagram Analytics/{record_name}",
        json=payload,
        headers=headers
    )

    print("Updated Existing Record — Status:", update_response.status_code)
    print(update_response.json())

    if update_response.status_code not in (200, 201):
        print("Update FAILED:", update_response.text)

else:
    payload["doctype"] = "Instagram Analytics"

    create_response = requests.post(
        f"{ERP_URL}/api/resource/Instagram Analytics",
        json=payload,
        headers=headers
    )

    print("Created New Record — Status:", create_response.status_code)
    print(create_response.json())

    if create_response.status_code not in (200, 201):
        print("Create FAILED:", create_response.text)