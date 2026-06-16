"""
poll_leads.py
Backfill + backup lead poller (runs in GitHub Actions).

Uses the user ACCESS_TOKEN to call /me/accounts (gets each Page + its own Page
token), then reads each Page's forms and leads with that Page token. One user
token therefore covers every Page.

Each lead is tagged with the product it came from (derived from the form name)
and upserted into ERPNext via lead_mapper (creates new, updates older ones).

Only leads created on/after LEADS_SINCE are imported (default 2026-01-01).
"""

import os
import requests

import lead_mapper

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
GRAPH = "v25.0"
LEADS_SINCE = os.getenv("LEADS_SINCE", "2026-01-01")
MAX_PER_FORM = 5000


def product_from_form(form_name):
    """Turn a Meta form name into a short, clean product label."""
    f = (form_name or "").lower()
    if "ecofoam" in f or "puf" in f or "panel" in f:
        return "PUF Panel"
    if "cold storage" in f:
        return "Cold Storage"
    if "dehydrator" in f:
        return "Solar Food Dehydrator"
    if "solar tree" in f:
        return "Solar Tree"
    if "dryer" in f:
        return "Solar Dryer"
    return form_name or None


def get_pages():
    r = requests.get(
        f"https://graph.facebook.com/{GRAPH}/me/accounts",
        params={"access_token": ACCESS_TOKEN, "fields": "name,id,access_token", "limit": 100},
        timeout=30,
    )
    d = r.json()
    if d.get("error"):
        print("ERROR /me/accounts:", d["error"].get("message"))
        return []
    return d.get("data", [])


def get_forms(page_id, page_token):
    r = requests.get(
        f"https://graph.facebook.com/{GRAPH}/{page_id}/leadgen_forms",
        params={"access_token": page_token, "fields": "id,name", "limit": 100},
        timeout=30,
    )
    d = r.json()
    if d.get("error"):
        print(f"  SKIP forms on {page_id}: {d['error'].get('message')}")
        return []
    return d.get("data", [])


def iter_leads(form_id, page_token):
    """Yield leads newest-first, stopping at LEADS_SINCE or the safety cap."""
    url = f"https://graph.facebook.com/{GRAPH}/{form_id}/leads"
    params = {"access_token": page_token, "limit": 100}
    count = 0
    while url and count < MAX_PER_FORM:
        r = requests.get(url, params=params, timeout=30)
        d = r.json()
        if d.get("error"):
            print(f"    leads error on {form_id}: {d['error'].get('message')}")
            return
        for ld in d.get("data", []):
            if (ld.get("created_time", "")[:10]) < LEADS_SINCE:
                return
            count += 1
            yield ld
        url = (d.get("paging") or {}).get("next")
        params = None


def main():
    for k, v in {
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "ERP_URL": lead_mapper.ERP_URL,
        "API_KEY": lead_mapper.API_KEY,
        "API_SECRET": lead_mapper.API_SECRET,
    }.items():
        if not v:
            raise EnvironmentError(f"Missing environment variable: {k}")

    pages = get_pages()
    print(f"Found {len(pages)} page(s) via /me/accounts. Importing leads since {LEADS_SINCE}.")

    created = updated = skipped = failed = 0
    for p in pages:
        ptoken = p.get("access_token")
        if not ptoken:
            continue
        for f in get_forms(p["id"], ptoken):
            product = product_from_form(f.get("name"))
            n = 0
            for ld in iter_leads(f["id"], ptoken):
                n += 1
                ok, msg = lead_mapper.create_lead(ld.get("field_data", []), ld.get("id"), product)
                if ok and msg == "Lead updated":
                    updated += 1
                elif ok:
                    created += 1
                elif msg.startswith("Duplicate"):
                    skipped += 1
                else:
                    failed += 1
                    print("    FAILED:", msg)
            if n:
                print(f"  {p['name']} / {f.get('name')} [{product}]: {n} lead(s)")

    print(f"DONE - created={created}, updated={updated}, skipped(dupe)={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
