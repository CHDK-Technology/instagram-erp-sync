from flask import Flask, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")


@app.route("/", methods=["GET"])
def home():
    return "Instagram Webhook Running"


# META WEBHOOK VERIFICATION
@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if token == VERIFY_TOKEN:
        return challenge

    return "Verification failed"


# RECEIVE WEBHOOK EVENTS
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("Webhook Event Received:")
    print(data)

    # FETCH INSTAGRAM DATA
    url = f"https://graph.facebook.com/v25.0/{INSTAGRAM_ID}"

    params = {
        "fields": "username,followers_count,media_count",
        "access_token": ACCESS_TOKEN
    }

    response = requests.get(url, params=params)
    instagram_data = response.json()

    headers = {
        "Authorization": f"token {API_KEY}:{API_SECRET}"
    }

    payload = {
        "doctype": "Instagram Analytics",
        "instagram_username": instagram_data.get("username"),
        "followers_count": instagram_data.get("followers_count"),
        "media_count": instagram_data.get("media_count"),
        "last_sync": str(datetime.now())
    }

    requests.post(
        f"{ERP_URL}/api/resource/Instagram Analytics",
        json=payload,
        headers=headers
    )

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)