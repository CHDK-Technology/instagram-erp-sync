from flask import Flask, request
import requests
import os

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Ecosaras2026")

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

    try:

        data = request.json

        print("WEBHOOK DATA:", data)

        for entry in data.get("entry", []):

            for change in entry.get("changes", []):

                print("CHANGE:", change)

                if change.get("field") != "leadgen":
                    continue

                leadgen_id = change["value"]["leadgen_id"]

                print("LEADGEN EVENT RECEIVED")
                print("LEADGEN ID:", leadgen_id)

                lead_url = f"https://graph.facebook.com/v25.0/{leadgen_id}"

                lead_data = requests.get(
                    lead_url,
                    params={
                        "access_token": ACCESS_TOKEN
                    }
                ).json()

                print("LEAD DATA:", lead_data)

                if lead_data.get("error"):
                    print("META ERROR:", lead_data)
                    continue

                field_data = lead_data.get("field_data", [])

                lead = {
                    "doctype": "Lead",
                    "company": "Instagram Lead",
                    "last_name": "Instagram",
                    "source": "Instagram Campaign",
                    "lead_type": "Client",
                    "email_id": "instagram@lead.com",
                    "mobile_no": "0000000000"
                }

                for field in field_data:

                    name = field.get("name", "").lower()
                    values = field.get("values", [])

                    if not values:
                        continue

                    value = values[0]

                    print(f"FIELD: {name} = {value}")

                    if name in [
                        "full_name",
                        "full name",
                        "name",
                        "your_name",
                        "customer_name",
                        "contact_name",
                        "first_name"
                    ]:
                        lead["lead_name"] = value
                        lead["first_name"] = value

                    elif name in [
                        "phone_number",
                        "phone",
                        "mobile_number",
                        "phone number"
                    ]:
                        lead["mobile_no"] = value

                    elif name in [
                        "email",
                        "email_address"
                    ]:
                        lead["email_id"] = value

                    else:
                        lead[name] = value

                if not lead.get("lead_name"):
                    lead["lead_name"] = "Instagram Lead"

                print("FINAL ERP LEAD PAYLOAD:", lead)

                response = requests.post(
                    f"{ERP_URL}/api/resource/Lead",
                    json=lead,
                    headers=headers
                )

                print("ERP STATUS CODE:", response.status_code)
                print("ERP RESPONSE:", response.text)

        return "EVENT_RECEIVED", 200

    except Exception as e:

        print("ERROR:", str(e))
        return "ERROR", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)