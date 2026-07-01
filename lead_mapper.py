"""
lead_mapper.py

Shared logic for turning a Meta Lead-Ads submission into an ERPNext Lead.
Used by BOTH:
  - webhook.py     (real-time, runs on Render)
  - poll_leads.py  (15-min backup poller, runs in GitHub Actions)

Each Meta answer is mapped to its own ERPNext field so leads are fully
structured and filterable:
  - company_name          = the person's name (drives Title / Customer Name columns)
  - custom_product_name   = the SPECIFIC product the customer picked
                             ("vegetable_cooler" -> "Vegetable Cooler"); falls back
                             to the form-derived category when the form doesn't ask.
  - custom_module_capacity = capacity answer (e.g. "5-20 Kg (Solar Dryer)")
  - custom_purpose         = purpose answer (e.g. "Farming")
  - custom_farm_size       = land / farm size answer (e.g. "2-5 Acre")
  - city / state           = mapped to their own fields
  - custom_message         = the full raw Q&A, kept as a complete record
  - custom_products_services_notes = same raw Q&A, mirrored into the
                             Products/Services Notes field  # ⚠️ confirm real fieldname
"""

import os
import re
import requests

ERP_URL = os.getenv("ERP_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

COMPANY = "Eco Saras Group"
SOURCE = "Instagram Campaign"
STATUS = "Lead"
CUSTOM_LEAD_TYPE = "B2C"

DEDUP_FIELD = "custom_meta_lead_id"
NOTES_FIELD = "custom_message"
PRODUCTS_NOTES_FIELD = "custom_productsservices_notes"  # ⚠️ confirm via Customize Form on Lead
PRODUCT_FIELD = "custom_product_name"
CAPACITY_FIELD = "custom_module_capacity"
PURPOSE_FIELD = "custom_purpose"
FARM_FIELD = "custom_farm_size"

NAME_KEYS = ("full_name", "name", "full name", "first_name")
PHONE_KEYS = ("phone_number", "phone", "mobile_number", "mobile", "contact_number")
EMAIL_KEYS = ("email", "email_address")
CITY_KEYS = ("city", "town/city", "town", "city/town", "town_city")
STATE_KEYS = ("state", "province")

# Fields ERPNext owns from Meta; used to decide whether an existing lead needs updating.
MANAGED_FIELDS = ("company_name", "city", "state", PRODUCT_FIELD, CAPACITY_FIELD, PURPOSE_FIELD, FARM_FIELD, PRODUCTS_NOTES_FIELD)


def get_headers():
    return {"Authorization": f"token {API_KEY}:{API_SECRET}", "Content-Type": "application/json"}


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


def humanize_value(value):
    """'vegetable_cooler' -> 'Vegetable Cooler'; '5-20_kg_(solar_dryer)' -> '5-20 Kg (Solar Dryer)'."""
    return re.sub(r"\s+", " ", str(value).replace("_", " ")).strip().title()


def parse_field_data(field_data):
    parsed = {}
    for field in field_data or []:
        name = (field.get("name") or "").lower().strip()
        values = field.get("values") or []
        if name and values:
            parsed[name] = clean_text(values[0])
    return parsed


def find_answer(parsed, *substrings):
    """Return the answer to the first question whose key contains any of the substrings."""
    for k, v in parsed.items():
        if v and any(s in k for s in substrings):
            return v
    return None


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

    # The specific product the customer picked; else fall back to the form-derived category.
    product_answer = find_answer(parsed, "which_product", "product_are_you_interested")
    if product_answer:
        product = humanize_value(product_answer)

    capacity = find_answer(parsed, "capacity")
    purpose = find_answer(parsed, "purpose")
    farm_size = find_answer(parsed, "size_of_your_farm", "farm_size", "land_size", "size_of_land")

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
        "company": COMPANY,
        "company_name": full_name,
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
    if product:
        lead[PRODUCT_FIELD] = product
    if capacity:
        lead[CAPACITY_FIELD] = humanize_value(capacity)
    if purpose:
        lead[PURPOSE_FIELD] = humanize_value(purpose)
    if farm_size:
        lead[FARM_FIELD] = humanize_value(farm_size)
    if notes:
        lead[NOTES_FIELD] = notes
        lead[PRODUCTS_NOTES_FIELD] = notes  # mirror the same Q&A into Products/Services Notes
    if leadgen_id:
        lead[DEDUP_FIELD] = str(leadgen_id)

    return lead


def find_existing(leadgen_id):
    """Return the existing Lead's managed-field values (dict incl. 'name'), or None."""
    if not leadgen_id:
        return None

    fields = '["name","company_name","city","state","' + '","'.join(
        [PRODUCT_FIELD, CAPACITY_FIELD, PURPOSE_FIELD, FARM_FIELD, PRODUCTS_NOTES_FIELD]) + '"]'

    try:
        resp = requests.get(
            f"{ERP_URL}/api/resource/Lead",
            params={
                "filters": f'[["{DEDUP_FIELD}","=","{leadgen_id}"]]',
                "fields": fields,
                "limit_page_length": 1,
            },
            headers=get_headers(),
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            if data:
                return data[0]
        return None
    except Exception as e:
        print("FIND EXISTING FAILED (continuing):", e)
        return None


def create_lead(field_data, leadgen_id=None, product=None):
    """
    Upsert one lead into ERPNext.
      - new                     -> POST (create)
      - exists, fields differ   -> PUT (fill name/product/capacity/purpose/farm/city/state/notes)
      - exists, all fields match -> skip

    Returns (changed: bool, message: str).
    """
    parsed = parse_field_data(field_data)
    payload = build_lead_payload(parsed, leadgen_id, product)

    existing = find_existing(leadgen_id)

    if existing:
        want = {k: payload[k] for k in MANAGED_FIELDS if k in payload}
        if all(existing.get(k) == v for k, v in want.items()):
            return False, f"Duplicate skipped (leadgen_id={leadgen_id})"

        try:
            resp = requests.put(
                f"{ERP_URL}/api/resource/Lead/{existing['name']}",
                json=want,
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
