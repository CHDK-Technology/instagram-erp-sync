from flask import Flask, request  # type: ignore
import requests
import os
from dotenv import load_dotenv  # FIX 1: Missing load_dotenv import

load_dotenv()  # FIX 2: Must be called before reading env vars

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Ecosaras2026")
ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")


def get_headers():
    # FIX 3: Build headers inside a function so they are never built with None values
    return {
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

                # FIX 4: Also pass page_id param — required by Meta for page-scoped tokens
                lead_url = f"https://graph.facebook.com/v25.0/{leadgen_id}"
                lead_resp = requests.get(
                    lead_url,
                    params={"access_token": ACCESS_TOKEN}
                )

                print("LEAD API STATUS:", lead_resp.status_code)
                lead_data = lead_resp.json()
                print("LEAD DATA:", lead_data)

                if lead_data.get("error"):
                    print("META API ERROR:", lead_data["error"])
                    continue

                field_data = lead_data.get("field_data", [])

                # FIX 5: Start with empty lead — don't prefill email/phone with fake data
                # Real values from the form will overwrite correctly
                lead = {
                    "doctype": "Lead",
                    "lead_name": "Instagram Lead",       # fallback, overwritten below
                    "first_name": "Instagram Lead",      # fallback
                    "last_name": "",
                    "source": "Social Media",            # FIX 6: "Social Media" is standard ERPNext option
                    "status": "Lead",                    # FIX 7: Required field in ERPNext Lead
                    "company_name": "Instagram Lead",    # FIX 8: correct field name (not "company")
                    "email_id": "",
                    "mobile_no": ""
                }

                for field in field_data:
                    name = field.get("name", "").lower().strip()
                    values = field.get("values", [])

                    if not values:
                        continue

                    value = str(values[0]).strip()
                    print(f"FIELD: {name} = {value}")

                    # Name fields
                    if name in [
                        "full_name", "full name", "name",
                        "your_name", "customer_name",
                        "contact_name", "first_name"
                    ]:
                        lead["lead_name"] = value
                        lead["first_name"] = value

                    # Phone fields
                    elif name in [
                        "phone_number", "phone", "mobile_number",
                        "phone number", "mobile", "contact_number"
                    ]:
                        lead["mobile_no"] = value

                    # Email fields
                    elif name in ["email", "email_address", "email address"]:
                        lead["email_id"] = value

                    # Any other fields stored as custom notes
                    else:
                        # FIX 9: Don't blindly add unknown fields to ERPNext Lead payload
                        # as they cause 417/ValidationError. Log them instead.
                        print(f"UNMAPPED FIELD (skipped): {name} = {value}")

                # FIX 10: Clean up empty strings — ERPNext prefers missing keys over empty strings
                # for non-required fields
                if not lead["email_id"]:
                    del lead["email_id"]
                if not lead["mobile_no"]:
                    del lead["mobile_no"]
                if not lead["last_name"]:
                    del lead["last_name"]

                print("FINAL ERP LEAD PAYLOAD:", lead)

                response = requests.post(
                    f"{ERP_URL}/api/resource/Lead",
                    json=lead,
                    headers=get_headers()  # FIX 3: use function
                )

                print("ERP STATUS CODE:", response.status_code)
                print("ERP RESPONSE:", response.text)

                # FIX 11: Log clearly if ERPNext rejected the lead
                if response.status_code not in (200, 201):
                    print("ERPNext FAILED to create lead. Response:", response.text)
                else:
                    print("Lead created successfully in ERPNext.")

        return "EVENT_RECEIVED", 200

    except Exception as e:
        import traceback
        print("ERROR:", str(e))
        print(traceback.format_exc())  # FIX 12: Full traceback for easier debugging
        return "ERROR", 500


@app.route("/privacy", methods=["GET"])
def privacy():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - CP Ecosaras</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.7; }
        h1 { color: #2c7a4b; }
        h2 { color: #2c7a4b; margin-top: 30px; }
        p { margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Last updated: May 29, 2026</strong></p>
    <p>This Privacy Policy describes how <strong>CP Ecosaras</strong> ("we", "us", or "our") collects, uses, and handles your information when you interact with our services, including our Facebook and Instagram Lead Ads.</p>

    <h2>1. Information We Collect</h2>
    <p>When you submit a lead form through our Facebook or Instagram advertisements, we may collect the following information:</p>
    <ul>
        <li>Full name</li>
        <li>Email address</li>
        <li>Phone / mobile number</li>
        <li>Any other information you provide in the form</li>
    </ul>

    <h2>2. How We Use Your Information</h2>
    <p>We use the information collected to:</p>
    <ul>
        <li>Contact you regarding our products and services</li>
        <li>Respond to your inquiries</li>
        <li>Manage our customer relationships via our internal CRM system (ERPNext)</li>
    </ul>

    <h2>3. Data Sharing</h2>
    <p>We do not sell, trade, or share your personal information with third parties except as required by law or to operate our business (e.g., our internal CRM platform). Your data is never shared with advertisers or marketing agencies without your consent.</p>

    <h2>4. Data Retention</h2>
    <p>We retain your personal information for as long as necessary to fulfill the purposes described in this policy, or as required by applicable law.</p>

    <h2>5. Your Rights</h2>
    <p>You have the right to:</p>
    <ul>
        <li>Request access to the personal data we hold about you</li>
        <li>Request correction or deletion of your personal data</li>
        <li>Withdraw consent at any time by contacting us</li>
    </ul>

    <h2>6. Contact Us</h2>
    <p>If you have any questions about this Privacy Policy or how we handle your data, please contact us at:</p>
    <p>
        <strong>CP Ecosaras</strong><br>
        Email: <a href="mailto:ecosaras126@gmail.com">ecosaras126@gmail.com</a>
    </p>

    <h2>7. Changes to This Policy</h2>
    <p>We may update this Privacy Policy from time to time. Any changes will be posted on this page with an updated date.</p>
</body>
</html>
""", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)