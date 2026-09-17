#!/usr/bin/env python3
"""Dagelijkse bezettingsscraper voor Big Billies - Zandvoort."""

import datetime
import json
import os
import pathlib
import random
import re
import sys
import time
import traceback

from scrape import build_proxy, goto_retry, parse_slots_from_text


BOOKING_URL = "https://www.billiessauna.com/nl/book-now"
SERVICE_TITLE = "Big Billies - Zandvoort"
NEXT_SERVICE_TITLE = "The Barrel - Zandvoort"
MAX_CAPACITY = 6
PRICE = 20

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}
DATE_RE = re.compile(
    r"(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|"
    r"maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\s*,?\s*"
    r"(\d{1,2})\s+([a-z]+)\s+(\d{4})",
    re.I,
)


def service_section(text):
    """Isoleer de gewone Big Billies-kaart en sluit Mini Steam/The Barrel uit."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    try:
        start = next(i for i, line in enumerate(lines) if line.casefold() == SERVICE_TITLE.casefold())
    except StopIteration:
        return ""
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].casefold() == NEXT_SERVICE_TITLE.casefold()),
        len(lines),
    )
    return "\n".join(lines[start:end])


def displayed_date(section):
    match = DATE_RE.search(section)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.casefold())
    if not month:
        return None
    return datetime.date(int(year), month, int(day))


def find_widget(page):
    for frame in page.frames:
        if "bookeo.com" not in (frame.url or ""):
            continue
        try:
            text = frame.inner_text("body")
        except Exception:
            continue
        lowered = text.lower()
        if "inactive for too long" in lowered:
            return None, "SESSION_EXPIRED"
        if "unauthorized ip" in lowered:
            return None, "IP_BLOCKED"
        section = service_section(text)
        if section and re.search(r"\b\d{1,2}:\d{2}\b", section):
            return section, None
    return None, None


def scrape_once(browser, proxy, target, debug=False):
    context = browser.new_context(
        viewport={"width": 1366, "height": 2400},
        user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        locale="nl-NL",
        timezone_id="Europe/Amsterdam",
        extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
        proxy=proxy,
    )
    context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = context.new_page()

    blocked_types = ("image", "media", "font")
    blocked_hosts = ("google-analytics", "googletagmanager", "doubleclick", "hotjar", "clarity.ms",
                     "facebook", "sentry.io", "wixstatic.com/media")

    def route(request_route):
        request = request_route.request
        if request.resource_type in blocked_types or any(host in request.url for host in blocked_hosts):
            return request_route.abort()
        return request_route.continue_()

    page.route("**/*", route)
    section = ""
    try:
        goto_retry(page, BOOKING_URL)
        for selector in ["button:has-text('Accepteren')", "button:has-text('Accept')", ".cmplz-accept"]:
            try:
                page.click(selector, timeout=1800)
                break
            except Exception:
                pass

        error = None
        for _ in range(20):
            page.wait_for_timeout(random.randint(1800, 2800))
            section, state = find_widget(page)
            if state == "SESSION_EXPIRED":
                error = "sessie geweigerd (Bookeo bot-detectie)"
                break
            if state == "IP_BLOCKED":
                error = "IP geblokkeerd (proxy)"
                break
            if section:
                break

        if debug:
            directory = pathlib.Path("debug")
            directory.mkdir(exist_ok=True)
            (directory / "billies.txt").write_text(section or "", encoding="utf-8")

        if error:
            return {"date": target.isoformat(), "slots": [], "error": error}
        if not section:
            return {"date": target.isoformat(), "slots": [], "error": "Big Billies-kaart niet gevonden"}

        shown = displayed_date(section)
        if shown and shown != target:
            return {
                "date": target.isoformat(), "displayed_date": shown.isoformat(), "slots": [],
                "error": f"widget toont {shown}, verwacht {target}",
            }

        slots = parse_slots_from_text(section)
        slots = [slot for slot in slots if 0 <= slot["available"] <= MAX_CAPACITY]
        if not slots:
            return {"date": target.isoformat(), "slots": [], "error": "geen tijdsloten herkend"}
        return {
            "date": target.isoformat(),
            "displayed_date": shown.isoformat() if shown else None,
            "slots": slots,
            "error": None,
        }
    except Exception as exc:
        return {"date": target.isoformat(), "slots": [], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    finally:
        context.close()


def target_date_from_env():
    value = os.environ.get("TARGET_DATE")
    if value:
        return datetime.date.fromisoformat(value)
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).date()


def main():
    from playwright.sync_api import sync_playwright

    target = target_date_from_env()
    run_label = os.environ.get("RUN_LABEL", "")
    debug = os.environ.get("DEBUG") == "1"
    headless = os.environ.get("HEADLESS") == "1"
    to_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))

    print(
        f"== Big Billies scraper == datum={target} meetmoment={run_label or '-'} "
        f"headed={not headless} proxy={'ja' if os.environ.get('PROXY_URL') else 'NEE'} "
        f"supabase={'ja' if to_supabase else 'nee'}"
    )
    result = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            proxy=build_proxy("billies"),
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        for attempt in range(1, 4):
            result = scrape_once(browser, build_proxy("billies"), target, debug=debug)
            print(f"Poging {attempt}: {result['error'] or str(len(result['slots'])) + ' slots'}")
            if not result["error"] and result["slots"]:
                break
            time.sleep(random.uniform(3, 6))
        browser.close()

    if not result or result["error"] or not result["slots"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    if to_supabase:
        try:
            import billies_supa
            billies_supa.write_result(result, target, run_label)
        except Exception as exc:
            print("Supabase-fout:", exc)
            traceback.print_exc()
            sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"== klaar: {len(result['slots'])} tijdsloten ==")


if __name__ == "__main__":
    main()
