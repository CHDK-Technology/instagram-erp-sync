"""
webhook.py
Real-time Meta Lead-Ads receiver. Deployed on Render: gunicorn webhook:app

Meta calls this the instant a lead form is submitted (leadgen webhook).
It fetches the full lead from the Graph API, then hands it to lead_mapper
to dedup + create the ERPNext Lead.

IMPORTANT (Render env vars — set these in the Render dashboard, NOT GitHub):
  ERP_URL, API_KEY, API_SECRET, ACCESS_TOKEN, VERIFY_TOKEN, APP_SECRET
The ACCESS_TOKEN here is SEPARATE from the GitHub secret and must be the same
new non-expiring System User token (with leads_retrieval scope).
"""

import os
import hmac
import hashlib
import traceback

import requests
from flask import Flask, request
from dotenv import load_dotenv

import lead_mapper  # shared mapping + ERPNext create/dedup

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Ecosaras2026")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
APP_SECRET = os.getenv("APP_SECRET")  # Meta App Secret, used to verify payloads

GRAPH_VERSION = "v25.0"


def verify_signature(raw_body, signature_header):
    """
    Verify Meta's X-Hub-Signature-256 header.
    If APP_SECRET is not configured, we log a warning and allow the request
    (so the webhook keeps working until you add the secret). Once APP_SECRET
    is set, invalid signatures are rejected.
    """
    if not APP_SECRET:
        print("WARNING: APP_SECRET not set — skipping signature check.")
        return True
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.route("/webhook", methods=["GET"])
def verify():
    """Meta subscription handshake."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data()  # raw bytes needed for signature check

    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        print("REJECTED: bad X-Hub-Signature-256")
        return "Invalid signature", 403

    try:
        data = request.json or {}
        print("WEBHOOK DATA:", data)

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "leadgen":
                    continue

                leadgen_id = change.get("value", {}).get("leadgen_id")
                if not leadgen_id:
                    continue
                print("LEADGEN EVENT — ID:", leadgen_id)

                # Fetch the full lead from Meta
                lead_resp = requests.get(
                    f"https://graph.facebook.com/{GRAPH_VERSION}/{leadgen_id}",
                    params={"access_token": ACCESS_TOKEN},
                    timeout=30,
                )
                lead_data = lead_resp.json()
                print("META STATUS:", lead_resp.status_code, "DATA:", lead_data)

                if lead_data.get("error"):
                    # Most common cause: expired/invalid ACCESS_TOKEN on Render.
                    print("META API ERROR:", lead_data["error"])
                    continue

                created, msg = lead_mapper.create_lead(
                    lead_data.get("field_data", []), leadgen_id
                )
                print(("OK: " if created else "SKIP/FAIL: ") + msg)

        # Always 200 so Meta doesn't hammer retries; failures are logged above.
        return "EVENT_RECEIVED", 200

    except Exception as e:
        print("ERROR:", e)
        print(traceback.format_exc())
        return "ERROR", 500


@app.route("/privacy", methods=["GET"])
def privacy():
    return """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Policy - CP Ecosaras</title>
<style>body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;color:#333;line-height:1.7}h1,h2{color:#2c7a4b}h2{margin-top:30px}</style>
</head><body>
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
</body></html>
""", 200


@app.route("/", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
