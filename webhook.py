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


# WEBHOOK VERIFICATION

@app.route("/webhook", methods=["GET"])
def verify():

    print("VERIFY REQUEST RECEIVED")
    print("ARGS:", request.args)

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print("MODE:", mode)
    print("TOKEN:", token)

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK VERIFIED SUCCESSFULLY")
            return challenge, 200

    print("VERIFICATION FAILED")
    return "Verification failed", 403



# WEBHOOK EVENTS

@app.route("/webhook", methods=["POST"])
def webhook():

    print("POST RECEIVED")

    data = request.json
    print("Webhook Data:", data)

    try:

        for entry in data.get("entry", []):

            changes = entry.get("changes", [])

            for change in changes:

                print("CHANGE:", change)

                if change.get("field") == "leadgen":

                    print("LEADGEN EVENT RECEIVED")

                    leadgen_id = change["value"]["leadgen_id"]

                    print("LEADGEN ID:", leadgen_id)

                    # FETCH LEAD DATA FROM META

                    lead_url = f"https://graph.facebook.com/v25.0/{leadgen_id}"

                    params = {
                        "access_token": ACCESS_TOKEN
                    }

                    lead_data = requests.get(
                        lead_url,
                        params=params
                    ).json()

                    print("LEAD DATA:", lead_data)

                    field_data = lead_data.get("field_data", [])

                    # ERP LEAD PAYLOAD

                    lead = {
                        "doctype": "Lead",
                        "source": "Instagram Campaign"
                    }

                    for field in field_data:

                        name = field.get("name")
                        values = field.get("values", [])

                        if values:

                            value = values[0]

                            print(f"FIELD: {name} = {value}")

                            # NAME FIELDS

                            if name in [
                                "full_name",
                                "name",
                                "your_name"
                            ]:

                                lead["lead_name"] = value
                                lead["first_name"] = value

                            # PHONE FIELDS

                            elif name in [
                                "phone_number",
                                "phone",
                                "mobile_number"
                            ]:

                                lead["mobile_no"] = value

                            # EMAIL FIELDS

                            elif name in [
                                "email",
                                "email_address"
                            ]:

                                lead["email_id"] = value

                            # OTHER FIELDS

                            else:

                                lead[name] = value

                    # FALLBACK NAME

                    if not lead.get("lead_name"):

                        lead["lead_name"] = "Instagram Lead"

                    print("FINAL ERP LEAD PAYLOAD:", lead)

                    # SEND TO ERP

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
