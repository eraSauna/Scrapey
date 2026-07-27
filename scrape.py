#!/usr/bin/env python3
"""
Kuuma bezetting-scraper.

Leest per locatie de Bookeo-widget uit (aantal BESCHIKBARE plekken per tijdslot)
en schrijft dat naar Supabase.

Belangrijke bevindingen die het gedrag bepalen:
- Bookeo blokkeert datacenter/geflagde IP's  -> residentiele proxy (sticky NL-sessie).
- Bookeo blokkeert headless browsers ("session inactive") -> we draaien HEADED
  (in de cloud onder xvfb). New-headless werkt niet.
- Playwright+proxy geeft soms ERR_PROXY_AUTH_UNSUPPORTED -> we retryen de navigatie.

Config (env vars):
  PROXY_URL       http://user:pass@host:poort   (residentiele proxy; verplicht in de cloud)
  PROXY_COUNTRY   land voor IPRoyal-geo (default nl)
  SUPABASE_URL    https://xxxx.supabase.co       (leeg = niet schrijven, alleen JSON printen)
  SUPABASE_KEY    service_role-key
  TARGET_DATE     YYYY-MM-DD  (default: vandaag in Europe/Amsterdam)
  ONLY            komma-lijst van locatie-keys (default: alle)
  DEBUG           "1" -> sla per locatie de frame-tekst op in ./debug/
  HEADLESS        "1" -> forceer headless (alleen voor debug; Bookeo blokkeert dit)
  RUN_LABEL       vrij label (bv. "03:00" / "12:00")

Lokaal testen (zonder Supabase):
  PROXY_URL=... DEBUG=1 ONLY=ams-bjork ./venv/bin/python scrape.py
"""
import os, re, sys, json, time, random, string, datetime, pathlib, traceback

from playwright.sync_api import sync_playwright
from locations import LOCATIONS, page_url


# ---------------------------------------------------------------- proxy
def parse_proxy(url):
    if not url:
        return None
    m = re.match(r"^(?P<scheme>https?)://(?:(?P<user>[^:@]+):(?P<pw>[^@]+)@)?(?P<host>[^:/]+):(?P<port>\d+)", url.strip())
    if not m:
        raise ValueError(f"PROXY_URL niet te parsen: {url!r}")
    d = {"server": f"{m['scheme']}://{m['host']}:{m['port']}"}
    if m["user"]:
        d["username"] = m["user"]; d["password"] = m["pw"]
    return d


def build_proxy():
    """Basis-creds uit PROXY_URL; voor IPRoyal voegen we NL-geo + sticky sessie toe."""
    d = parse_proxy(os.environ.get("PROXY_URL", ""))
    if not d:
        return None
    if "iproyal" in d["server"] and d.get("password") and "_session-" not in d["password"]:
        country = os.environ.get("PROXY_COUNTRY", "nl")
        sess = "kuuma" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        d["password"] = f'{d["password"]}_country-{country}_session-{sess}_lifetime-30m'
    return d


def goto_retry(page, url, n=5):
    for k in range(n):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            if "PROXY_AUTH" in str(e) and k < n - 1:
                time.sleep(2 + k); continue
            raise


# ---------------------------------------------------------------- parsing
TIME_RE = re.compile(r"^\s*(\d{1,2}[:.]\d{2})\s*$")
AVAIL_RE = re.compile(r"available[:\s]*?(\d+)", re.I)
FULL_RE = re.compile(r"\b(full|vol|volgeboekt|niet beschikbaar|not available)\b", re.I)
DATE_RE = re.compile(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\s*\n?\s*(\d{1,2})\s+([a-z]+)\s+(\d{4})", re.I)


def parse_slots_from_text(text):
    """Widget-tekst -> [{time, available}]. Formaat: tijd op 1 regel, dan 'Available: N' of 'FULL'."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, line in enumerate(lines):
        m = TIME_RE.match(line)
        if not m:
            continue
        t = m.group(1).replace(".", ":")
        hh, mm = t.split(":")
        t = f"{int(hh):02d}:{mm}"
        window = " ".join(lines[i + 1:i + 3])
        a = AVAIL_RE.search(window)
        if a:
            out.append({"time": t, "available": int(a.group(1))})
        elif FULL_RE.search(window):
            out.append({"time": t, "available": 0})
    seen, uniq = set(), []
    for s in out:
        if s["time"] in seen:
            continue
        seen.add(s["time"]); uniq.append(s)
    return uniq


def find_slot_frame(page):
    for f in page.frames:
        u = f.url or ""
        if "bookeo.com" in u and "widgetProvider" not in u:
            try:
                t = f.inner_text("body")
            except Exception:
                t = ""
            if re.search(r"\b\d{1,2}:\d{2}\b", t) and (AVAIL_RE.search(t) or FULL_RE.search(t)):
                return f, t
            if "inactive for too long" in t.lower():
                return None, "SESSION_EXPIRED"
            if "unauthorized ip" in t.lower():
                return None, "IP_BLOCKED"
    return None, ""


def scrape_location(browser, proxy, loc, target_date, debug=False):
    res = {"key": loc["key"], "naam": loc["naam"], "date": target_date.isoformat(),
           "slots": [], "displayed_date": None, "error": None}
    ctx = browser.new_context(
        viewport={"width": 1366, "height": 2200},
        user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        locale="nl-NL", timezone_id="Europe/Amsterdam",
        extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
        proxy=proxy,
    )
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.new_page()

    def route(r):
        if r.request.resource_type in ("image", "media", "font"):
            return r.abort()
        return r.continue_()
    page.route("**/*", route)

    text = ""
    try:
        goto_retry(page, page_url(loc))
        for sel in ["button:has-text('Accepteren')", "text=Accepteren", ".cmplz-accept"]:
            try:
                page.click(sel, timeout=2500); break
            except Exception:
                pass
        try:
            page.eval_on_selector("#bookeo_position", "el=>el.scrollIntoView()")
        except Exception:
            pass

        for _ in range(18):  # tot ~50s
            page.wait_for_timeout(random.randint(2000, 3300))
            frame, t = find_slot_frame(page)
            if t == "SESSION_EXPIRED":
                res["error"] = "sessie geweigerd (headless/bot-detectie?)"; break
            if t == "IP_BLOCKED":
                res["error"] = "IP geblokkeerd (proxy?)"; break
            if frame:
                text = t; break

        if debug:
            d = pathlib.Path("debug"); d.mkdir(exist_ok=True)
            (d / f"{loc['key']}.txt").write_text(text or "")

        if res["error"]:
            return res
        if not text:
            res["error"] = "geen slots-frame gevonden"; return res

        dm = DATE_RE.search(text)
        if dm:
            res["displayed_date"] = re.sub(r"\s+", " ", dm.group(0))
        res["slots"] = parse_slots_from_text(text)
        if not res["slots"]:
            res["error"] = "frame gevonden maar geen slots herkend"
        page.wait_for_timeout(random.randint(700, 1900))
        return res
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return res
    finally:
        ctx.close()


def target_date_from_env():
    td = os.environ.get("TARGET_DATE")
    if td:
        return datetime.date.fromisoformat(td)
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date()


def main():
    target = target_date_from_env()
    only = {k.strip() for k in os.environ.get("ONLY", "").split(",") if k.strip()}
    debug = os.environ.get("DEBUG") == "1"
    headless = os.environ.get("HEADLESS") == "1"   # Bookeo blokkeert headless; alleen voor debug
    run_label = os.environ.get("RUN_LABEL", "")
    proxy = build_proxy()
    to_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))

    locs = [l for l in LOCATIONS if (not only or l["key"] in only)]
    random.shuffle(locs)
    print(f"== Kuuma scraper == datum={target} locaties={len(locs)} headed={not headless} proxy={'ja' if proxy else 'NEE'} supabase={'ja' if to_supabase else 'nee'}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless, proxy=proxy,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        for i, loc in enumerate(locs):
            r = scrape_location(browser, proxy, loc, target, debug=debug)
            if r["error"] or not r["slots"]:          # 1x opnieuw bij transiente hapering
                time.sleep(random.uniform(3, 6))
                r2 = scrape_location(browser, proxy, loc, target, debug=debug)
                if not r2["error"] and r2["slots"]:
                    r = r2
            print(f"  - {loc['naam']:22} {r['error'] or str(len(r['slots']))+' slots '+(r['displayed_date'] or '')}")
            results.append(r)
            if i < len(locs) - 1:
                time.sleep(random.uniform(7, 16))
        browser.close()

    if to_supabase:
        try:
            import supa
            supa.write_results(results, target, run_label)
        except Exception as e:
            print("Supabase-fout:", e); traceback.print_exc()
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    ok = sum(1 for r in results if not r["error"])
    print(f"== klaar: {ok}/{len(results)} gelukt ==")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
