from flask import Flask, request
import requests
import os

app = Flask(__name__)

VERIFY_TOKEN = "Ecosaras2026"

ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

headers = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json"
}

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200

    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Webhook Data:", data)

    try:
        for entry in data.get("entry", []):

            # LEAD FORM DATA
            changes = entry.get("changes", [])

            for change in changes:
                if change.get("field") == "leadgen":

                    leadgen_id = change["value"]["leadgen_id"]

                    lead_url = f"https://graph.facebook.com/v25.0/{leadgen_id}"
                    params = {
                        "access_token": ACCESS_TOKEN
                    }

                    lead_data = requests.get(lead_url, params=params).json()

                    print("Lead Data:", lead_data)

                    field_data = lead_data.get("field_data", [])

                    lead = {
                        "doctype": "Lead"
                    }

                    for field in field_data:
                        name = field.get("name")
                        values = field.get("values", [])

                        if values:
                            value = values[0]

                            if name == "full_name":
                                lead["lead_name"] = value

                            elif name == "phone_number":
                                lead["mobile_no"] = value

                            elif name == "email":
                                lead["email_id"] = value

                            else:
                                lead[name] = value

                    lead["source"] = "Instagram Campaign"

                    response = requests.post(
                        f"{ERP_URL}/api/resource/Lead",
                        json=lead,
                        headers=headers
                    )

                    print("ERPNext Response:", response.text)

        return "EVENT_RECEIVED", 200

    except Exception as e:
        print("ERROR:", str(e))
        return "ERROR", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)