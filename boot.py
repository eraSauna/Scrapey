#!/usr/bin/env python3
"""
De Saunaboot (Kortenhoef) — aparte scraper, volledig los van Kuuma.

Eén pagina, één boot. Leest per tijdslot of de boot bezet is:
  - "Beschikbaar: 8"  -> vrij (0 geboekt)
  - "WACHTLIJST" of minder dan 8 vrij -> geboekt (privéboot = hele boot bezet)
Omzet = slotprijs van de geboekte slots.

Env: PROXY_URL, SUPABASE_URL, SUPABASE_KEY, TARGET_DATE, RUN_LABEL, DEBUG, HEADLESS.
Schrijft naar tabel boot_beschikbaarheid (upsert op datum+slot_time).
"""
import os, re, sys, json, time, random, string, datetime, pathlib, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

URL = "https://www.desaunaboot.nl/boeken"
CAP = 8  # hele boot; 8 getoond = vrij

MND = {"januari":1,"februari":2,"maart":3,"april":4,"mei":5,"juni":6,"juli":7,
       "augustus":8,"september":9,"oktober":10,"november":11,"december":12,
       "january":1,"february":2,"march":3,"may":5,"june":6,"july":7,"october":10}
# datum staat als "DINSDAG\n18 AUGUSTUS 2026" — anker op de weekdagnaam,
# anders pakt de regex per ongeluk het gasten-getal vóór "AUGUSTUS 2026".
DATE_RE = re.compile(
    r"(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*\n?\s*"
    r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", re.I)
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
PRICE_RE = re.compile(r"[€€]\s?(\d+)")
WL_RE = re.compile(r"wachtlijst|waitlist|\bvol\b|\bfull\b|niet beschikbaar|not available", re.I)
AV_RE = re.compile(r"beschikb\w*[:\s]*?(\d+)", re.I)


def build_proxy():
    raw = os.environ.get("PROXY_URL", "")
    m = re.match(r"^(https?)://(?:([^:@]+):([^@]+)@)?([^:/]+):(\d+)", raw)
    if not m:
        return None
    d = {"server": f"{m[1]}://{m[4]}:{m[5]}"}
    if m[2]:
        pw = m[3]
        if "iproyal" in m[4] and "_session-" not in pw:
            sess = "boot" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
            pw = f"{pw}_country-nl_session-{sess}_lifetime-30m"
        d["username"] = m[2]; d["password"] = pw
    return d


def goto_retry(page, url, n=4):
    last = None
    for k in range(n):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            last = e; time.sleep(2 + 2 * k)
    raise last


def find_frame(page):
    for f in page.frames:
        u = f.url or ""
        if "bookeo.com" in u and "widgetProvider" not in u:
            try: t = f.inner_text("body")
            except Exception: t = ""
            low = t.lower()
            if "unauthorized ip" in low: return None, "IP_BLOCKED"
            if "inactive for too long" in low: return None, "SESSION_EXPIRED"
            if re.search(r"\d{1,2}[:.]\d{2}", t) and (AV_RE.search(t) or WL_RE.search(t)):
                return f, t
    return None, ""


def parse_slots(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, line in enumerate(lines):
        m = TIME_RE.match(line)
        if not m:
            continue
        t = f"{int(m.group(1)):02d}:{m.group(2)}"
        window = " ".join(lines[i + 1:i + 3])
        prijs = int(PRICE_RE.search(window).group(1)) if PRICE_RE.search(window) else None
        wl = bool(WL_RE.search(window))
        av = int(AV_RE.search(window).group(1)) if AV_RE.search(window) else None
        geboekt = wl or (av is not None and av < CAP)
        out.append({"time": t, "beschikbaar": av, "wachtlijst": wl, "prijs": prijs, "geboekt": geboekt})
    # dedup op tijd
    seen, uniq = set(), []
    for s in out:
        if s["time"] in seen: continue
        seen.add(s["time"]); uniq.append(s)
    return uniq


def displayed_date(text):
    m = DATE_RE.search(text or "")
    if not m: return None
    mnd = MND.get(m.group(2).lower())
    if not mnd: return None
    try: return datetime.date(int(m.group(3)), mnd, int(m.group(1)))
    except Exception: return None


def scrape(target, run_label, debug=False):
    proxy = build_proxy()
    headless = os.environ.get("HEADLESS") == "1"
    res = {"date": target.isoformat(), "displayed_date": None, "slots": [], "error": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, proxy=proxy,
                                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 2400}, locale="nl-NL",
                                  timezone_id="Europe/Amsterdam",
                                  extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
                                  user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.new_page()
        page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
        try:
            goto_retry(page, URL)
            for sel in ["button:has-text('Accepteren')", "text=Accepteren", "button:has-text('Alle')", ".cmplz-accept"]:
                try: page.click(sel, timeout=2500); break
                except Exception: pass

            frame, text = None, ""
            for _ in range(18):
                page.wait_for_timeout(random.randint(2200, 3300))
                frame, text = find_frame(page)
                if text in ("IP_BLOCKED", "SESSION_EXPIRED"):
                    res["error"] = text; break
                if frame and len(parse_slots(text)) >= 1:
                    break

            if debug:
                d = pathlib.Path("debug"); d.mkdir(exist_ok=True)
                (d / "boot.txt").write_text(text or "")
                if frame:
                    try: (d / "boot.html").write_text(frame.content())
                    except Exception: pass

            if res["error"]:
                return res
            if not frame:
                res["error"] = "geen Bookeo-frame gevonden"; return res

            res["displayed_date"] = (displayed_date(text) or target).isoformat()
            res["slots"] = parse_slots(text)
            if not res["slots"]:
                res["error"] = "geen slots herkend"
            page.wait_for_timeout(random.randint(700, 1600))
            return res
        except Exception as e:
            res["error"] = f"{type(e).__name__}: {str(e)[:120]}"; return res
        finally:
            browser.close()


def to_supabase(res, run_label):
    url = os.environ["SUPABASE_URL"].rstrip("/"); key = os.environ["SUPABASE_KEY"]
    datum = res["displayed_date"] or res["date"]
    rows = [{
        "datum": datum, "slot_time": s["time"], "beschikbaar": s["beschikbaar"],
        "wachtlijst": s["wachtlijst"], "geboekt": s["geboekt"], "prijs": s["prijs"],
        "run_label": run_label,
    } for s in res["slots"]]
    if not rows:
        print("Supabase: geen rijen"); return
    req = urllib.request.Request(
        f"{url}/rest/v1/boot_beschikbaarheid?on_conflict=datum,slot_time",
        data=json.dumps(rows).encode(), method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Supabase: {len(rows)} rijen ge-upsert (HTTP {r.status})")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase HTTP {e.code}: {e.read().decode()[:300]}") from None


def main():
    td = os.environ.get("TARGET_DATE")
    target = datetime.date.fromisoformat(td) if td else (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date()
    run_label = os.environ.get("RUN_LABEL", "ochtend")
    debug = os.environ.get("DEBUG") == "1"
    to_sb = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))
    print(f"== Saunaboot scraper == doel={target} run={run_label} proxy={'ja' if build_proxy() else 'NEE'} supabase={'ja' if to_sb else 'nee'}")

    res = scrape(target, run_label, debug=debug)
    geboekt = sum(1 for s in res["slots"] if s["geboekt"])
    print(f"  displayed={res['displayed_date']} slots={len(res['slots'])} geboekt={geboekt} {res['error'] or ''}")

    if to_sb and not res["error"]:
        try: to_supabase(res, run_label)
        except Exception as e: print("Supabase-fout:", e)
    else:
        print(json.dumps(res, ensure_ascii=False, indent=2))

    if res["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
