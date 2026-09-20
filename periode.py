#!/usr/bin/env python3
"""Kuuma-bezetting uit het publieke Periode-overzicht naar Supabase.

De Kuuma-pagina publiceert een kortlevende WordPress-nonce. We halen die bij
elke run opnieuw op en vragen daarna in één call alle actieve sauna's en
drop-in-tijdsloten op. Er is geen browser of proxy nodig.
"""

import datetime
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo

from locations import BY_LOCATION_AND_NAME, BY_SERVICE_ID


OVERVIEW_URL = os.environ.get(
    "KUUMA_OVERVIEW_URL", "https://kuuma.nl/boek-nu/marineterrein-bjork/"
)
USER_AGENT = "Mozilla/5.0 (compatible; eraSauna-occupancy-monitor/2.0)"


def _request(url, timeout=30, attempts=3):
    """GET met begrensde retries voor tijdelijke netwerk- en serverfouten."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.7",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Ophalen mislukt na {attempts} pogingen: {last}") from last


def extract_periode_config(html):
    """Lees het JSON-object na ``periodeData =`` zonder fragiele HTML-parser."""
    marker = re.search(r"(?:var\s+)?periodeData\s*=\s*", html)
    if not marker:
        raise ValueError("periodeData-config niet gevonden op de Kuuma-pagina")
    try:
        config, _ = json.JSONDecoder().raw_decode(html, marker.end())
    except json.JSONDecodeError as exc:
        raise ValueError(f"periodeData-config is geen geldige JSON: {exc}") from exc
    if not config.get("ajaxUrl") or not config.get("nonce"):
        raise ValueError("periodeData mist ajaxUrl of nonce")
    return config


def fetch_day(target):
    html = _request(OVERVIEW_URL).decode("utf-8", errors="replace")
    config = extract_periode_config(html)
    query = urllib.parse.urlencode(
        {
            "action": "periode_get_day",
            "nonce": config["nonce"],
            "lang": config.get("lang", "nl"),
            "date": target.isoformat(),
        }
    )
    separator = "&" if "?" in config["ajaxUrl"] else "?"
    payload = json.loads(_request(config["ajaxUrl"] + separator + query))
    if payload.get("success") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError(f"Periode gaf geen succesvolle response: {str(payload)[:300]}")
    data = payload["data"]
    if data.get("date") != target.isoformat():
        raise RuntimeError(
            f"Periode gaf datum {data.get('date')!r}, verwacht {target.isoformat()!r}"
        )
    if not isinstance(data.get("saunas"), list):
        raise RuntimeError("Periode-response mist de sauna-lijst")
    return data


def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def identify_sauna(sauna, location_counts):
    """Behoud bestaande keys; maak voor toekomstige sauna's een stabiele key."""
    known = BY_SERVICE_ID.get(str(sauna.get("id")))
    if not known:
        known = BY_LOCATION_AND_NAME.get(
            (str(sauna.get("location_id", "")), str(sauna.get("name", "")).casefold())
        )
    if known:
        return known["key"], known["naam"], False

    location_id = slugify(str(sauna.get("location_id") or "kuuma"))
    name = str(sauna.get("name") or location_id or "Nieuwe Kuuma-sauna")
    # Een locatie met meerdere sauna's moet per sauna meetbaar blijven.
    key = location_id
    if location_counts[str(sauna.get("location_id"))] > 1:
        key = f"{location_id}-{slugify(name)}"
    return key, name, True


def parse_results(data, only=None):
    saunas = data.get("saunas", [])
    location_counts = Counter(str(s.get("location_id")) for s in saunas)
    location_names = {
        str(loc.get("id")): str(loc.get("name") or loc.get("id"))
        for loc in data.get("locations", [])
    }
    results = []
    seen_keys = set()

    for sauna in saunas:
        key, name, discovered = identify_sauna(sauna, location_counts)
        if only and key not in only:
            continue
        if key in seen_keys:
            raise RuntimeError(f"Dubbele locatie-key uit Periode: {key}")
        seen_keys.add(key)

        try:
            capacity = int(sauna["capacity"])
            default_price = float(sauna["price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Ongeldige capaciteit/prijs voor {name}: {exc}") from exc
        if capacity <= 0 or default_price < 0:
            raise RuntimeError(f"Ongeldige capaciteit/prijs voor {name}")

        slots = []
        seen_times = set()
        for slot in sauna.get("slots", []):
            if slot.get("type") != "drop-in":
                continue
            slot_time = str(slot.get("time", ""))
            if not re.fullmatch(r"\d{2}:\d{2}", slot_time):
                raise RuntimeError(f"Ongeldige slottijd voor {name}: {slot_time!r}")
            if slot_time in seen_times:
                raise RuntimeError(f"Dubbel drop-in-slot voor {name}: {slot_time}")
            seen_times.add(slot_time)
            try:
                available = int(slot["available"])
                price = float(slot.get("price", default_price))
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Ongeldig slot voor {name} {slot_time}: {exc}") from exc
            if not 0 <= available <= capacity:
                raise RuntimeError(
                    f"Beschikbaarheid buiten bereik voor {name} {slot_time}: "
                    f"{available}/{capacity}"
                )
            slots.append({"time": slot_time, "available": available, "price": price})

        if not slots:
            # Locaties die Periode alvast kent maar nog niet boekbaar zijn, verschijnen
            # niet als actieve sauna. Een actieve sauna zonder drop-in-slots is verdacht.
            raise RuntimeError(f"Geen drop-in-slots ontvangen voor actieve sauna {name}")

        permalink = str(sauna.get("permalink") or "")
        path = urllib.parse.urlparse(permalink).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1] if path else key
        service_id = str(sauna.get("id") or "")
        location_id = str(sauna.get("location_id") or "")
        results.append(
            {
                "key": key,
                "naam": name,
                "date": data["date"],
                "capacity": capacity,
                "price": default_price,
                "slots": slots,
                "error": None,
                "provider": "periode",
                "provider_location_id": location_id,
                "provider_service_id": service_id,
                "provider_location_name": location_names.get(location_id, location_id),
                "slug": slug,
                "permalink": permalink,
                "discovered": discovered,
            }
        )
    return results


def target_date_from_env():
    value = os.environ.get("TARGET_DATE")
    if value:
        return datetime.date.fromisoformat(value)
    return datetime.datetime.now(ZoneInfo("Europe/Amsterdam")).date()


def main():
    target = target_date_from_env()
    only = {item.strip() for item in os.environ.get("ONLY", "").split(",") if item.strip()}
    run_label = os.environ.get("RUN_LABEL", "")
    to_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))

    print(
        f"== Kuuma Periode-scraper == datum={target} "
        f"supabase={'ja' if to_supabase else 'nee'}"
    )
    data = fetch_day(target)
    results = parse_results(data, only=only)
    if not results:
        raise RuntimeError("Geen actieve Kuuma-sauna's gevonden")

    for result in results:
        marker = " NIEUW" if result["discovered"] else ""
        print(
            f"  - {result['naam']:26} {len(result['slots']):2} slots, "
            f"cap {result['capacity']}, EUR {result['price']:.2f}{marker}"
        )

    active_location_ids = {str(sauna.get("location_id")) for sauna in data.get("saunas", [])}
    inactive = sorted(
        str(loc.get("name")) for loc in data.get("locations", [])
        if str(loc.get("id")) not in active_location_ids
    )
    if inactive and not only:
        print("  - nog niet actief in Periode: " + ", ".join(inactive))

    if to_supabase:
        import supa

        supa.write_results(results, target, run_label)
    elif os.environ.get("SUMMARY_ONLY") != "1":
        print(json.dumps(results, ensure_ascii=False, indent=2))

    print(f"== klaar: {len(results)} sauna's, {sum(len(r['slots']) for r in results)} slots ==")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FOUT: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
