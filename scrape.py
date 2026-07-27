#!/usr/bin/env python3
"""
Kuuma bezetting-scraper.

Leest per locatie de Bookeo-widget uit (aantal BESCHIKBARE plekken per tijdslot)
en schrijft dat naar een Google Sheet. Draait via een residentiele proxy om de
IP-blokkade van Bookeo te omzeilen.

Config (env vars):
  PROXY_URL      http://user:pass@host:poort   (residentiele proxy; verplicht in de cloud)
  SHEET_ID       Google Sheet id                (leeg = niet naar Sheets schrijven)
  GCP_SA_KEY     JSON van de service-account    (of pad via GCP_SA_KEY_FILE)
  TARGET_DATE    YYYY-MM-DD  (default: vandaag in Europe/Amsterdam)
  ONLY           komma-lijst van locatie-keys (default: alle)
  DEBUG          "1" -> sla per locatie de frame-HTML op in ./debug/
  RUN_LABEL      vrij label (bv. "03:00" / "12:00") -> tijdstempel in de sheet

Lokaal testen (zonder Sheets):
  PROXY_URL=... DEBUG=1 ONLY=ams-bjork ./venv/bin/python scrape.py
"""
import os, re, sys, json, time, datetime, pathlib, traceback

from playwright.sync_api import sync_playwright
from locations import LOCATIONS, page_url

AMS = datetime.timezone(datetime.timedelta(hours=2))  # indicatief; exacte tz in Actions via TARGET_DATE


# ---------------------------------------------------------------- helpers
def parse_proxy(url):
    """http://user:pass@host:port -> playwright proxy dict, of None."""
    if not url:
        return None
    m = re.match(r"^(?P<scheme>https?)://(?:(?P<user>[^:@]+):(?P<pw>[^@]+)@)?(?P<host>[^:/]+):(?P<port>\d+)", url.strip())
    if not m:
        raise ValueError(f"PROXY_URL niet te parsen: {url!r}")
    d = {"server": f"{m['scheme']}://{m['host']}:{m['port']}"}
    if m["user"]:
        d["username"] = m["user"]; d["password"] = m["pw"]
    return d


TIME_RE = re.compile(r"^\s*(\d{1,2}[:.]\d{2})\s*$")
AVAIL_RE = re.compile(r"available[:\s]*?(\d+)", re.I)
FULL_RE = re.compile(r"\b(full|vol|volgeboekt)\b", re.I)
DATE_RE = re.compile(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)[^0-9]{0,4}(\d{1,2})\s+([a-z]+)\s+(\d{4})", re.I)


def parse_slots_from_text(text):
    """
    VOORLOPIG. Zet widget-tekst om naar [{time, available}].
    Elk slot toont een tijd (7:00) en daaronder 'Available: N' of 'FULL'.
    We lopen regel voor regel; bij een tijd kijken we in het volgende venster
    naar Available/FULL. Wordt definitief gemaakt zodra we de echte DOM zien.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, line in enumerate(lines):
        m = TIME_RE.match(line)
        if not m:
            # soms staat 'tijd' en 'Available' op dezelfde regel
            m2 = re.match(r"^(\d{1,2}[:.]\d{2})\b(.*)$", line)
            if not m2:
                continue
            tstr, rest = m2.group(1), m2.group(2)
            window = rest
        else:
            tstr = m.group(1)
            window = " ".join(lines[i + 1:i + 3])
        t = tstr.replace(".", ":")
        hh, mm = t.split(":")
        t = f"{int(hh):02d}:{mm}"
        if FULL_RE.search(window) and not AVAIL_RE.search(window):
            out.append({"time": t, "available": 0})
            continue
        a = AVAIL_RE.search(window)
        if a:
            out.append({"time": t, "available": int(a.group(1))})
    # dedup op tijd (eerste voorkomen)
    seen, uniq = set(), []
    for s in out:
        if s["time"] in seen:
            continue
        seen.add(s["time"]); uniq.append(s)
    return uniq


def find_booking_frame(page):
    for f in page.frames:
        u = f.url or ""
        if "bookeo.com" in u and "widgetProvider" in u:
            return f
    for f in page.frames:
        if "bookeo.com" in (f.url or ""):
            return f
    return None


def scrape_location(context, loc, target_date, debug=False):
    """Return dict: {key, naam, date, slots:[{time,available}], displayed_date, error}."""
    res = {"key": loc["key"], "naam": loc["naam"], "date": target_date.isoformat(),
           "slots": [], "displayed_date": None, "error": None}
    page = context.new_page()
    # data besparen: blokkeer zware resources (widget heeft alleen document/js/xhr/css nodig)
    def route(r):
        if r.request.resource_type in ("image", "media", "font"):
            return r.abort()
        return r.continue_()
    page.route("**/*", route)
    try:
        page.goto(page_url(loc), wait_until="domcontentloaded", timeout=60000)
        for sel in ["button:has-text('Accepteren')", "text=Accepteren", ".cmplz-accept"]:
            try:
                page.click(sel, timeout=2500); break
            except Exception:
                pass
        # widget in beeld + tijd om te renderen
        try:
            page.eval_on_selector("#bookeo_position", "el=>el.scrollIntoView()")
        except Exception:
            pass

        frame = None
        text = ""
        for _ in range(16):  # tot ~40s wachten op slots
            page.wait_for_timeout(2500)
            frame = find_booking_frame(page)
            if not frame:
                continue
            try:
                text = frame.inner_text("body")
            except Exception:
                text = ""
            if "unauthorized ip" in text.lower():
                res["error"] = "IP geblokkeerd door Bookeo (geen/verkeerde proxy?)"
                break
            if AVAIL_RE.search(text) or FULL_RE.search(text) or re.search(r"\d{1,2}:\d{2}", text):
                if len(parse_slots_from_text(text)) >= 2:
                    break

        if debug:
            d = pathlib.Path("debug"); d.mkdir(exist_ok=True)
            (d / f"{loc['key']}.txt").write_text(text or "")
            if frame:
                try:
                    (d / f"{loc['key']}.html").write_text(frame.content())
                except Exception:
                    pass

        if res["error"]:
            return res
        if not frame:
            res["error"] = "geen Bookeo-frame gevonden"; return res

        dm = DATE_RE.search(text or "")
        if dm:
            res["displayed_date"] = dm.group(0)
        res["slots"] = parse_slots_from_text(text or "")
        if not res["slots"]:
            res["error"] = "geen slots herkend (selectors nog te finaliseren op echte DOM)"
        return res
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"
        return res
    finally:
        page.close()


def target_date_from_env():
    td = os.environ.get("TARGET_DATE")
    if td:
        return datetime.date.fromisoformat(td)
    # cloud draait in UTC; benader Amsterdam met +2 (zomer). Voor exacte tz zet je TARGET_DATE.
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date()


def main():
    target = target_date_from_env()
    only = {k.strip() for k in os.environ.get("ONLY", "").split(",") if k.strip()}
    debug = os.environ.get("DEBUG") == "1"
    run_label = os.environ.get("RUN_LABEL", "")
    proxy = parse_proxy(os.environ.get("PROXY_URL", ""))
    to_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))

    locs = [l for l in LOCATIONS if (not only or l["key"] in only)]
    print(f"== Kuuma scraper == datum={target} locaties={len(locs)} proxy={'ja' if proxy else 'NEE'} supabase={'ja' if to_supabase else 'nee'}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy=proxy)
        context = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            locale="nl-NL",
        )
        for loc in locs:
            r = scrape_location(context, loc, target, debug=debug)
            status = r["error"] or f"{len(r['slots'])} slots"
            print(f"  - {loc['naam']:22} {status}")
            results.append(r)
            time.sleep(4)  # rustig aan; gentler op Bookeo/proxy
        browser.close()

    # naar Supabase
    if to_supabase:
        try:
            import supa
            supa.write_results(results, target, run_label)
        except Exception as e:
            print("Supabase-fout:", e)
            traceback.print_exc()
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    ok = sum(1 for r in results if not r["error"])
    print(f"== klaar: {ok}/{len(results)} gelukt ==")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
