"""
lead_mapper.py
Shared logic for turning a Meta Lead-Ads submission into an ERPNext Lead.

Used by BOTH:
  - webhook.py    (real-time, runs on Render)
  - poll_leads.py (15-min backup poller, runs in GitHub Actions)

Readability design:
  - company_name is set to the PERSON'S name, so the Lead list "Title" and
    "Customer Name" columns show the customer (not the parent company). The
    internal `company` link still points to Eco Saras Group.
  - custom_product_name holds the product (drives the "Product Name" column).
  - city / state are mapped to their own fields; the rest of the answers go to
    the Message field.
"""

import os
import re
import requests

ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

COMPANY = "Eco Saras Group"          # internal Company link
SOURCE = "Instagram Campaign"
STATUS = "Lead"
CUSTOM_LEAD_TYPE = "B2C"
DEDUP_FIELD = "custom_meta_lead_id"
NOTES_FIELD = "custom_message"
PRODUCT_FIELD = "custom_product_name"

NAME_KEYS = ("full_name", "name", "full name", "first_name")
PHONE_KEYS = ("phone_number", "phone", "mobile_number", "mobile", "contact_number")
EMAIL_KEYS = ("email", "email_address")
CITY_KEYS = ("city", "town/city", "town", "city/town", "town_city")
STATE_KEYS = ("state", "province")


def get_headers():
    return {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json",
    }


def clean_text(value):
    if value is None:
        return None
    value = re.sub(r"[<>\"'\\]", "", str(value)).strip()
    return value or None


def is_valid_phone(value):
    if not value:
        return False
    return len(re.sub(r"[^0-9]", "", value)) >= 7


def humanize(key):
    return key.replace("_", " ").strip().title()


def parse_field_data(field_data):
    parsed = {}
    for field in field_data or []:
        name = (field.get("name") or "").lower().strip()
        values = field.get("values") or []
        if name and values:
            parsed[name] = clean_text(values[0])
    return parsed


def build_lead_payload(parsed, leadgen_id=None, product=None):
    full_name = next((parsed[k] for k in NAME_KEYS if parsed.get(k)), None) or "Instagram Lead"

    phone_raw = next((parsed[k] for k in PHONE_KEYS if parsed.get(k)), None)
    phone = None
    if phone_raw and is_valid_phone(phone_raw):
        phone = re.sub(r"[^0-9+\-\s()]", "", phone_raw).strip()

    email_raw = next((parsed[k] for k in EMAIL_KEYS if parsed.get(k)), None)
    email = email_raw if (email_raw and "@" in email_raw) else None

    city = next((parsed[k] for k in CITY_KEYS if parsed.get(k)), None)
    state = next((parsed[k] for k in STATE_KEYS if parsed.get(k)), None)

    handled = set(NAME_KEYS) | set(PHONE_KEYS) | set(EMAIL_KEYS) | set(CITY_KEYS) | set(STATE_KEYS)
    notes_parts = [f"{humanize(k)}: {v}" for k, v in parsed.items() if k not in handled and v]
    notes = " | ".join(notes_parts)

    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else full_name
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else first_name

    lead = {
        "doctype": "Lead",
        "lead_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "company": COMPANY,           # internal company (link)
        "company_name": full_name,    # -> Title / Customer Name = the person
        "source": SOURCE,
        "status": STATUS,
        "custom_lead_type": CUSTOM_LEAD_TYPE,
    }
    if phone:
        lead["mobile_no"] = phone
    if email:
        lead["email_id"] = email
    if city:
        lead["city"] = city
    if state:
        lead["state"] = state
    if notes:
        lead[NOTES_FIELD] = notes
    if product:
        lead[PRODUCT_FIELD] = product
    if leadgen_id:
        lead[DEDUP_FIELD] = str(leadgen_id)
    return lead


def find_existing(leadgen_id):
    """Return (name, company_name) for an existing Lead with this Meta id, else (None, None)."""
    if not leadgen_id:
        return None, None
    try:
        resp = requests.get(
            f"{ERP_URL}/api/resource/Lead",
            params={
                "filters": f'[["{DEDUP_FIELD}","=","{leadgen_id}"]]',
                "fields": '["name","company_name"]',
                "limit_page_length": 1,
            },
            headers=get_headers(),
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            if data:
                return data[0]["name"], data[0].get("company_name")
        return None, None
    except Exception as e:
        print("FIND EXISTING FAILED (continuing):", e)
        return None, None


def create_lead(field_data, leadgen_id=None, product=None):
    """
    Upsert one lead into ERPNext.
      - brand new                  -> POST (create)
      - exists, still old-format   -> PUT  (fix name/product/city/state; re-save recomputes title)
      - exists, already fixed      -> skip
    Returns (changed: bool, message: str).
    """
    parsed = parse_field_data(field_data)
    payload = build_lead_payload(parsed, leadgen_id, product)

    name, current_company = find_existing(leadgen_id)
    if name:
        if current_company == payload.get("company_name"):
            return False, f"Duplicate skipped (leadgen_id={leadgen_id})"
        update = {k: payload[k] for k in ("company_name", "city", "state", PRODUCT_FIELD) if k in payload}
        try:
            resp = requests.put(
                f"{ERP_URL}/api/resource/Lead/{name}",
                json=update,
                headers=get_headers(),
                timeout=30,
            )
        except Exception as e:
            return False, f"ERPNext update failed: {e}"
        if resp.status_code in (200, 201):
            return True, "Lead updated"
        return False, f"ERPNext update rejected ({resp.status_code}): {resp.text[:200]}"

    try:
        resp = requests.post(
            f"{ERP_URL}/api/resource/Lead",
            json=payload,
            headers=get_headers(),
            timeout=30,
        )
    except Exception as e:
        return False, f"ERPNext request failed: {e}"

    if resp.status_code in (200, 201):
        return True, "Lead created"
    return False, f"ERPNext rejected ({resp.status_code}): {resp.text[:300]}"
