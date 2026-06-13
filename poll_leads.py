"""
poll_leads.py
Backup lead poller - runs every 15 minutes in GitHub Actions.

Why this exists: the Render webhook is the primary, real-time path, but Render's
free tier sleeps when idle and can miss a webhook during a slow cold start. This
script re-pulls recent leads from every form on every Page and creates any that
aren't already in ERPNext (dedup via custom_meta_lead_id), so no lead is ever lost.

PAGE_ID may be a single Page ID OR several separated by commas, e.g.
  169905769529898,373953099129089,427508580450359
Pages the token can't access are skipped with a warning (the run still succeeds).

Required GitHub secrets:
  ACCESS_TOKEN  (non-expiring token with leads_retrieval + pages_show_list scope)
  PAGE_ID       (one or more Facebook Page IDs, comma-separated)
  ERP_URL, API_KEY, API_SECRET
"""

import os
import requests

import lead_mapper  # shared mapping + ERPNext create/dedup

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID", "")
GRAPH_VERSION = "v25.0"

# How many recent leads to check per form each run.
LEADS_PER_FORM = 50


def page_ids():
    """Parse PAGE_ID into a clean list (accepts commas and/or spaces)."""
    return [p.strip() for p in PAGE_ID.replace(",", " ").split() if p.strip()]


def get_forms(page_id):
    """List all lead-gen forms on one Page. Returns [] on error (logged)."""
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/leadgen_forms",
        params={"access_token": ACCESS_TOKEN, "limit": 100},
        timeout=30,
    )
    data = resp.json()
    if data.get("error"):
        print(f"  SKIP page {page_id}: {data['error'].get('message')}")
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
        print(f"  META ERROR fetching leads for form {form_id}: {data['error'].get('message')}")
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

    ids = page_ids()
    print(f"Checking {len(ids)} Page(s): {', '.join(ids)}")

    created = skipped = failed = total_forms = 0
    for page_id in ids:
        forms = get_forms(page_id)
        if forms:
            print(f"Page {page_id}: {len(forms)} form(s) -> {[f.get('name') for f in forms]}")
        total_forms += len(forms)
        for form in forms:
            leads = get_leads(form["id"])
            print(f"  Form '{form.get('name')}' ({form['id']}): {len(leads)} recent lead(s).")
            for lead in leads:
                ok, msg = lead_mapper.create_lead(lead.get("field_data", []), lead.get("id"))
                if ok:
                    created += 1
                elif msg.startswith("Duplicate"):
                    skipped += 1
                else:
                    failed += 1
                    print("  FAILED:", msg)

    print(f"DONE - pages={len(ids)}, forms={total_forms}, "
          f"created={created}, skipped(dupe)={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
