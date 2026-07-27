"""
Supabase-writer. Upsert van ruwe slot-metingen naar tabel slot_beschikbaarheid.
Conflict op (location_key, datum, slot_time) -> de 12:00-run overschrijft 03:00.
Alleen stdlib (urllib) — geen extra dependencies.
"""
import os, json, urllib.request, urllib.error
from locations import LOCATIONS

def _by_key(key):
    for l in LOCATIONS:
        if l["key"] == key:
            return l
    return None


def build_rows(results, target, run_label):
    rows = []
    for r in results:
        if r.get("error") or not r.get("slots"):
            continue
        loc = _by_key(r["key"])
        if not loc:
            continue
        for s in r["slots"]:
            rows.append({
                "location_key": loc["key"],
                "locatie": loc["naam"],
                "datum": target.isoformat(),
                "slot_time": s["time"],
                "beschikbaar": s["available"],
                "max_capaciteit": loc["maxdrop"],
                "prijs": loc["prijs"],
                "run_label": run_label,
            })
    return rows


def write_results(results, target, run_label):
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    rows = build_rows(results, target, run_label)
    if not rows:
        print("Supabase: geen rijen om te schrijven")
        return
    endpoint = f"{url}/rest/v1/slot_beschikbaarheid?on_conflict=location_key,datum,slot_time"
    data = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST", headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Supabase: {len(rows)} rijen ge-upsert (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase HTTP {e.code}: {e.read().decode()[:300]}") from None
