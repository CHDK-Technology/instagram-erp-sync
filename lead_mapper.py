"""
lead_mapper.py
Shared logic for turning a Meta Lead-Ads submission into an ERPNext Lead.

Used by BOTH:
  - webhook.py    (real-time, runs on Render)
  - poll_leads.py (15-min backup poller, runs in GitHub Actions)

Keeping the mapping in one place means a form change only has to be fixed once.
"""

import os
import re
import requests

# ── ERPNext connection (read from environment) ───────────────────────────────
ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# ── Fixed values (all verified to exist in your ERPNext) ─────────────────────
COMPANY = "Eco Saras Group"          # exists as a Company record
SOURCE = "Instagram Campaign"        # exists as a Lead Source
STATUS = "Lead"                      # valid Lead status
CUSTOM_LEAD_TYPE = "B2C"             # valid custom_lead_type option

# Custom Data field on the Lead doctype that stores Meta's lead id (for dedup).
# You must create this field once (see SETUP). If it is missing, dedup is skipped.
DEDUP_FIELD = "custom_meta_lead_id"

# Meta field names we recognise as the standard contact fields. Anything NOT in
# these lists is treated as a custom question and appended to lead_details.
NAME_KEYS = ("full_name", "name", "full name", "first_name")
PHONE_KEYS = ("phone_number", "phone", "mobile_number", "mobile", "contact_number")
EMAIL_KEYS = ("email", "email_address")


def get_headers():
    """Built at call time so env vars are guaranteed loaded."""
    return {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json",
    }


def clean_text(value):
    """Strip characters ERPNext rejects; return None if empty."""
    if value is None:
        return None
    value = re.sub(r"[<>\"'\\]", "", str(value)).strip()
    return value or None


def is_valid_phone(value):
    """A real phone has at least 7 digits (rejects Meta dummy text)."""
    if not value:
        return False
    return len(re.sub(r"[^0-9]", "", value)) >= 7


def humanize(key):
    """'what_capacity_are_you_interested_in' -> 'What Capacity Are You Interested In'."""
    return key.replace("_", " ").strip().title()


def parse_field_data(field_data):
    """Flatten Meta's field_data array into a lowercased {name: value} dict."""
    parsed = {}
    for field in field_data or []:
        name = (field.get("name") or "").lower().strip()
        values = field.get("values") or []
        if name and values:
            parsed[name] = clean_text(values[0])
    return parsed


def build_lead_payload(parsed, leadgen_id=None):
    """Map a parsed Meta submission to an ERPNext Lead payload."""
    # --- name ---
    full_name = next((parsed[k] for k in NAME_KEYS if parsed.get(k)), None) or "Instagram Lead"

    # --- phone (no fake fallback; left blank if absent/invalid) ---
    phone_raw = next((parsed[k] for k in PHONE_KEYS if parsed.get(k)), None)
    phone = None
    if phone_raw and is_valid_phone(phone_raw):
        phone = re.sub(r"[^0-9+\-\s()]", "", phone_raw).strip()

    # --- email ---
    email_raw = next((parsed[k] for k in EMAIL_KEYS if parsed.get(k)), None)
    email = email_raw if (email_raw and "@" in email_raw) else None

    # --- everything else -> notes (generic, survives form wording changes) ---
    handled = set(NAME_KEYS) | set(PHONE_KEYS) | set(EMAIL_KEYS)
    notes_parts = [
        f"{humanize(k)}: {v}"
        for k, v in parsed.items()
        if k not in handled and v
    ]
    notes = " | ".join(notes_parts)

    lead = {
        "doctype": "Lead",
        "lead_name": full_name,
        "first_name": full_name,
        "company": COMPANY,
        "company_name": COMPANY,
        "source": SOURCE,
        "status": STATUS,
        "custom_lead_type": CUSTOM_LEAD_TYPE,
    }
    if phone:
        lead["mobile_no"] = phone
    if email:
        lead["email_id"] = email
    if notes:
        lead["lead_details"] = notes
    if leadgen_id:
        lead[DEDUP_FIELD] = str(leadgen_id)
    return lead


def lead_already_exists(leadgen_id):
    """Return True if a Lead with this Meta id is already in ERPNext."""
    if not leadgen_id:
        return False
    try:
        resp = requests.get(
            f"{ERP_URL}/api/resource/Lead",
            params={"filters": f'[["{DEDUP_FIELD}","=","{leadgen_id}"]]', "limit_page_length": 1},
            headers=get_headers(),
            timeout=20,
        )
        if resp.status_code == 200:
            return bool(resp.json().get("data"))
        # If the dedup field doesn't exist yet, ERPNext errors -> skip dedup.
        return False
    except Exception as e:
        print("DEDUP CHECK FAILED (continuing):", e)
        return False


def create_lead(field_data, leadgen_id=None):
    """
    Full pipeline for one lead: dedup -> map -> POST to ERPNext.
    Returns (created: bool, message: str).
    """
    if lead_already_exists(leadgen_id):
        return False, f"Duplicate skipped (leadgen_id={leadgen_id})"

    parsed = parse_field_data(field_data)
    print("PARSED FIELDS:", parsed)
    payload = build_lead_payload(parsed, leadgen_id)
    print("ERP PAYLOAD:", payload)

    try:
        resp = requests.post(
            f"{ERP_URL}/api/resource/Lead",
            json=payload,
            headers=get_headers(),
            timeout=30,
        )
    except Exception as e:
        return False, f"ERPNext request failed: {e}"

    print("ERP STATUS:", resp.status_code)
    print("ERP RESPONSE:", resp.text[:500])
    if resp.status_code in (200, 201):
        return True, "Lead created"
    return False, f"ERPNext rejected ({resp.status_code}): {resp.text[:300]}"
