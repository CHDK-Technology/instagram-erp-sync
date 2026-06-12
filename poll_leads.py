"""
poll_leads.py
Backup lead poller — runs every 15 minutes in GitHub Actions.

Why this exists: the Render webhook is the primary, real-time path, but Render's
free tier sleeps when idle and can miss a webhook during a slow cold start.
This script re-pulls recent leads from every form on the Page and creates any
that aren't already in ERPNext (dedup via custom_meta_lead_id), so no lead is
ever lost. If the webhook already handled a lead, this safely skips it.

Required GitHub secrets:
  ACCESS_TOKEN  (same new non-expiring token, with leads_retrieval scope)
  PAGE_ID       (your Facebook Page ID)
  ERP_URL, API_KEY, API_SECRET
"""

import os
import requests

import lead_mapper  # shared mapping + ERPNext create/dedup

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
GRAPH_VERSION = "v25.0"

# How many recent leads to check per form each run. 15-min cadence means a
# handful at most; 50 is a safe buffer against bursts.
LEADS_PER_FORM = 50


def get_forms():
    """List all lead-gen forms on the Page."""
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/leadgen_forms",
        params={"access_token": ACCESS_TOKEN, "limit": 100},
        timeout=30,
    )
    data = resp.json()
    if data.get("error"):
        print("META ERROR listing forms:", data["error"])
        return []
    return data.get("data", [])


def get_leads(form_id):
    """Fetch recent leads for one form."""
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{form_id}/leads",
        params={"access_token": ACCESS_TOKEN, "limit": LEADS_PER_FORM},
        timeout=30,
    )
    data = resp.json()
    if data.get("error"):
        print(f"META ERROR fetching leads for form {form_id}:", data["error"])
        return []
    return data.get("data", [])


def main():
    missing = [k for k, v in {
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "PAGE_ID": PAGE_ID,
        "ERP_URL": lead_mapper.ERP_URL,
        "API_KEY": lead_mapper.API_KEY,
        "API_SECRET": lead_mapper.API_SECRET,
    }.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

    forms = get_forms()
    print(f"Found {len(forms)} form(s).")

    created = skipped = failed = 0
    for form in forms:
        form_id = form["id"]
        leads = get_leads(form_id)
        print(f"Form {form_id}: {len(leads)} recent lead(s).")
        for lead in leads:
            ok, msg = lead_mapper.create_lead(
                lead.get("field_data", []), lead.get("id")
            )
            if ok:
                created += 1
            elif msg.startswith("Duplicate"):
                skipped += 1
            else:
                failed += 1
                print("FAILED:", msg)

    print(f"DONE — created={created}, skipped(dupe)={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
