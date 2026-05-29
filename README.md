# instagram-erp-sync

Syncs Instagram leads (Meta Lead Ads webhook) and Instagram analytics into ERPNext.

---

## Setup

### 1. Environment Variables
Create a `.env` file (never commit this):

```
INSTAGRAM_ID=your_instagram_business_account_id
ACCESS_TOKEN=your_meta_long_lived_access_token
ERP_URL=https://yoursite.frappe.cloud
API_KEY=your_erpnext_api_key
API_SECRET=your_erpnext_api_secret
VERIFY_TOKEN=Ecosaras2026
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Deploy on Render
- **Start command:** `gunicorn webhook:app`
- **Port:** 10000

---

## Webhook Setup (Meta Developer Portal)

1. Go to your Meta App → Webhooks
2. Set callback URL: `https://instagram-erp-sync.onrender.com/webhook`
3. Set verify token: `Ecosaras2026`
4. Subscribe to `leadgen` field

---

## ERPNext Lead Field Mapping

| Meta Form Field | ERPNext Field |
|---|---|
| full_name / name / first_name | lead_name, first_name |
| phone / phone_number / mobile | mobile_no |
| email / email_address | email_id |

---

## Bugs Fixed

1. **`load_dotenv()` missing in webhook.py** — env vars were never loaded, so API_KEY/SECRET were `None`
2. **`headers` dict built at module load** (before env vars loaded) — moved to `get_headers()` function
3. **Hardcoded fallback email/phone** (`instagram@lead.com`, `0000000000`) — removed; real values from Meta form are used
4. **Unknown form fields sent to ERPNext** — caused 417 Validation errors; now logged and skipped
5. **`company` field** is not valid on ERPNext Lead doctype — fixed to `company_name`
6. **`source` value** `"Instagram Campaign"` may not match ERPNext picklist — changed to `"Social Media"` (standard)
7. **`status` field missing** — ERPNext Lead requires it; added `"Lead"` as default
8. **No error handling** on Meta API or ERPNext responses — added status code checks and full traceback logging
9. **Empty string fields** sent to ERPNext — cleaned up before POST to avoid validation errors