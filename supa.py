"""Supabase-writer en read-back-verificatie voor Kuuma-slotmetingen.

De actuele locatiemetadata wordt eerst ge-upsert. Daardoor werken nieuwe
Periode-locaties direct met de bestaande foreign key en dashboardviews.
"""
import os, json, urllib.parse, urllib.request, urllib.error


def build_rows(results, target, run_label):
    ochtend = (run_label or "").lower().startswith("ochtend")
    rows = []
    for r in results:
        if r.get("error") or not r.get("slots"):
            continue
        for s in r["slots"]:
            row = {
                "location_key": r["key"],
                "locatie": r["naam"],
                "datum": target.isoformat(),
                "slot_time": s["time"],
                "beschikbaar": s["available"],
                "max_capaciteit": r["capacity"],
                "prijs": s.get("price", r["price"]),
                "run_label": run_label,
            }
            # Alleen bij de ochtendrun de vroege stand vastleggen. De middagrun laat dit
            # veld weg, zodat de upsert de ochtendwaarde niet overschrijft.
            if ochtend:
                row["beschikbaar_ochtend"] = s["available"]
            rows.append(row)
    return rows


def build_location_rows(results):
    rows = []
    for r in results:
        if r.get("error") or not r.get("slots"):
            continue
        rows.append({
            "key": r["key"],
            "naam": r["naam"],
            "slug": r.get("slug") or r["key"],
            # De bestaande kolomnamen blijven staan om een risicovolle live
            # migratie te vermijden; ze bevatten nu de provider-identiteit.
            "bookeo_a": f"periode:{r.get('provider_location_id', '')}",
            "bookeo_type": r.get("provider_service_id") or "periode",
            "maxdrop": r["capacity"],
            "prijs": r["price"],
            "geopend_tot": None,
            "slots": [slot["time"] for slot in r["slots"]],
        })
    return rows


def _upsert(url, key, table, rows, on_conflict):
    if not rows:
        return
    endpoint = f"{url}/rest/v1/{table}?on_conflict={on_conflict}"
    req = urllib.request.Request(
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Supabase: {len(rows)} rijen naar {table} (HTTP {resp.status})")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {detail}") from None


def verify_results(url, key, results, target):
    expected = {
        (result["key"], slot["time"])
        for result in results if not result.get("error")
        for slot in result.get("slots", [])
    }
    location_keys = sorted({location_key for location_key, _ in expected})
    if not expected:
        raise RuntimeError("Supabase-verificatie heeft geen verwachte slots")
    quoted_keys = ",".join(f'"{value}"' for value in location_keys)
    query = urllib.parse.urlencode({
        "select": "location_key,slot_time",
        "datum": f"eq.{target.isoformat()}",
        "location_key": f"in.({quoted_keys})",
        "limit": "1000",
    })
    request = urllib.request.Request(
        f"{url}/rest/v1/slot_beschikbaarheid?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            stored_rows = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Supabase read-back HTTP {exc.code}: {detail}") from None
    stored = {(row["location_key"], row["slot_time"]) for row in stored_rows}
    missing = sorted(expected - stored)
    if missing:
        preview = ", ".join(f"{loc}/{slot}" for loc, slot in missing[:10])
        raise RuntimeError(f"Supabase read-back mist {len(missing)} slots: {preview}")
    print(
        f"Supabase verificatie OK: {len(expected)} slots, "
        f"{len(location_keys)} locaties (inclusief nieuwe locaties)"
    )


def write_results(results, target, run_label):
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    locations = build_location_rows(results)
    rows = build_rows(results, target, run_label)
    if not rows:
        raise RuntimeError("Supabase: geen geldige slotrijen om te schrijven")
    # Referenties moeten bestaan voordat de metingen met hun foreign key landen.
    _upsert(url, key, "locaties", locations, "key")
    _upsert(
        url, key, "slot_beschikbaarheid", rows,
        "location_key,datum,slot_time",
    )
    verify_results(url, key, results, target)
