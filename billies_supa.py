"""Schrijft Big Billies-slotmetingen naar Supabase."""

import json
import os
import urllib.error
import urllib.request

from billies import MAX_CAPACITY, PRICE


def build_rows(result, target, run_label):
    morning = (run_label or "").lower().startswith("ochtend")
    rows = []
    for slot in result.get("slots", []):
        row = {
            "datum": target.isoformat(),
            "slot_time": slot["time"],
            "beschikbaar": slot["available"],
            "max_capaciteit": MAX_CAPACITY,
            "prijs": PRICE,
            "run_label": run_label,
        }
        if morning:
            row["beschikbaar_ochtend"] = slot["available"]
        rows.append(row)
    return rows


def write_result(result, target, run_label):
    rows = build_rows(result, target, run_label)
    if not rows:
        raise RuntimeError("geen Big Billies-rijen om te schrijven")

    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    endpoint = f"{base_url}/rest/v1/billies_beschikbaarheid?on_conflict=datum,slot_time"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(rows).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"Supabase: {len(rows)} Big Billies-rijen ge-upsert (HTTP {response.status})")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Supabase HTTP {exc.code}: {exc.read().decode()[:300]}") from None
