from flask import Flask, request
import requests
import re
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Ecosaras2026")
ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")


def get_headers():
    return {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json"
    }


def clean_text(value):
    """Remove special characters ERPNext rejects and strip whitespace."""
    value = re.sub(r"[<>\"'\\]", "", str(value)).strip()
    return value if value else None


def is_valid_phone(value):
    """Check if value looks like a real phone number."""
    digits_only = re.sub(r"[^0-9]", "", value)
    return len(digits_only) >= 7


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
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

                if change.get("field") != "leadgen":
                    continue

                leadgen_id = change["value"]["leadgen_id"]
                print("LEADGEN EVENT RECEIVED — ID:", leadgen_id)

                lead_resp = requests.get(
                    f"https://graph.facebook.com/v25.0/{leadgen_id}",
                    params={"access_token": ACCESS_TOKEN}
                )

                print("META API STATUS:", lead_resp.status_code)
                lead_data = lead_resp.json()
                print("LEAD DATA:", lead_data)

                if lead_data.get("error"):
                    print("META API ERROR:", lead_data["error"])
                    continue

                # ── Parse all fields from Meta form ──────────────────────
                parsed = {}
                for field in lead_data.get("field_data", []):
                    name = field.get("name", "").lower().strip()
                    values = field.get("values", [])
                    if values:
                        parsed[name] = clean_text(values[0])

                print("PARSED FIELDS:", parsed)

                # ── Map Meta fields → ERPNext fields ─────────────────────
                full_name = (
                    parsed.get("full_name") or
                    parsed.get("name") or
                    parsed.get("full name") or
                    parsed.get("first_name") or
                    "Instagram Lead"
                )

                phone = (
                    parsed.get("phone_number") or
                    parsed.get("phone") or
                    parsed.get("mobile_number") or
                    parsed.get("mobile") or
                    parsed.get("contact_number") or
                    ""
                )

                email = (
                    parsed.get("email") or
                    parsed.get("email_address") or
                    ""
                )

                state = parsed.get("state") or ""

                purpose = (
                    parsed.get("what_is_your_primary_purpose_for_using_ecosaras_solar_dryer") or
                    parsed.get("primary_purpose") or
                    ""
                )

                capacity = (
                    parsed.get("what_capacity_of_solar_dryer_are_you_interested_in") or
                    parsed.get("capacity") or
                    ""
                )

                # ── Build notes from custom questions ────────────────────
                notes_parts = []
                if purpose:
                    notes_parts.append(f"Purpose: {purpose}")
                if capacity:
                    notes_parts.append(f"Capacity Interest: {capacity}")
                if state:
                    notes_parts.append(f"State: {state}")
                notes = " | ".join(notes_parts)

                # ── Build ERPNext Lead payload ────────────────────────────
                lead = {
                    "doctype": "Lead",
                    "lead_name": full_name,
                    "first_name": full_name,
                    "last_name": "Instagram",
                    "company_name": "Eco Saras Group",  # must match ERPNext company master
                    "source": "Instagram Campaign",      # exact ERPNext picklist value
                    "status": "Lead",                    # exact ERPNext picklist value
                    "lead_type": "B2C",                  # exact ERPNext picklist value
                }

                # Only add email if it looks real
                if email and "@" in email:
                    lead["email_id"] = email

                # Only add phone if it looks real
                if phone and is_valid_phone(phone):
                    clean_phone = re.sub(r"[^0-9+\-\s()]", "", phone).strip()
                    lead["mobile_no"] = clean_phone

                # Save custom question answers in lead_details (text field)
                if notes:
                    lead["lead_details"] = notes

                print("FINAL ERP PAYLOAD:", lead)

                response = requests.post(
                    f"{ERP_URL}/api/resource/Lead",
                    json=lead,
                    headers=get_headers()
                )

                print("ERP STATUS CODE:", response.status_code)
                print("ERP RESPONSE:", response.text)

                if response.status_code in (200, 201):
                    print("✅ Lead created successfully in ERPNext!")
                else:
                    print("❌ ERPNext FAILED to create lead.")

        return "EVENT_RECEIVED", 200

    except Exception as e:
        import traceback
        print("ERROR:", str(e))
        print(traceback.format_exc())
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
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Last updated: May 29, 2026</strong></p>
    <p>This Privacy Policy describes how <strong>CP Ecosaras</strong> collects, uses, and handles your information when you interact with our services, including our Facebook and Instagram Lead Ads.</p>
    <h2>1. Information We Collect</h2>
    <p>When you submit a lead form through our Facebook or Instagram advertisements, we may collect: Full name, Email address, Phone / mobile number, State, and any other information you provide.</p>
    <h2>2. How We Use Your Information</h2>
    <p>We use the information to contact you regarding our products and services, respond to your inquiries, and manage our customer relationships via our internal CRM system (ERPNext).</p>
    <h2>3. Data Sharing</h2>
    <p>We do not sell, trade, or share your personal information with third parties except as required by law or to operate our business.</p>
    <h2>4. Data Retention</h2>
    <p>We retain your personal information for as long as necessary to fulfill the purposes described in this policy.</p>
    <h2>5. Your Rights</h2>
    <p>You have the right to request access, correction, or deletion of your personal data by contacting us.</p>
    <h2>6. Contact Us</h2>
    <p><strong>CP Ecosaras</strong><br>Email: <a href="mailto:ecosaras126@gmail.com">ecosaras126@gmail.com</a></p>
</body>
</html>
""", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)