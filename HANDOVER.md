# Kuuma & Saunaboot bezetting-tracker — handover

Volledige uitleg van het systeem: wat het is, hoe het in elkaar zit, hoe je het gebruikt,
wijzigt en pusht. Geen wachtwoorden/keys in dit document — die staan in GitHub Secrets,
Supabase en je IPRoyal-account (zie "Accounts").

---

## 1. Wat het is

Drie **gescheiden** trackers die de bezetting/omzet van saunalocaties volgen:

- **Kuuma** — 10 actieve sauna's via Periode. 2× per dag gemeten.
- **Big Billies** — 1 sauna in Zandvoort. 2× per dag gemeten.
- **De Saunaboot** — 1 privé-saunaboot in Kortenhoef. 1× per dag gemeten.

De data van beide **kruist nooit**: aparte scrapers, aparte Supabase-tabellen, aparte
dashboard-sectie. Ze delen wel dezelfde infrastructuur (proxy, Supabase-project, Vercel).

---

## 2. Architectuur (dataflow)

```
GitHub Actions (cron)  ──►  Kuuma: HTTP/JSON  ──►  Periode-overzicht (alle sauna's in één call)
        │              Billies/Boot: Playwright + proxy ──► Bookeo-widget
        │                                            │
        │                       leest per tijdslot de beschikbaarheid ◄──────┘
        ▼
   schrijft (upsert) naar Supabase  ──►  SQL-views berekenen reserveringen/bezetting/omzet
        ▼
   Next.js-dashboard op Vercel  ◄── leest Supabase server-side met de secret key
```

**Waarom deze opzet:** Kuuma levert sinds september 2026 gestructureerde Periode-data en heeft
geen browser/proxy meer nodig. Bookeo blokkeert bij Billies/Boot nog wel datacenter-IP's en
headless browsers; alleen die scrapers gebruiken daarom IPRoyal en Chromium onder xvfb.

---

## 3. Repositories

| Repo | Lokaal pad | Inhoud |
|---|---|---|
| `eraSauna/Scrapey` (privé) | `~/Scrapey` | Beide scrapers + GitHub Actions-workflows + SQL-schema's |
| `eraSauna/kuuma-dashboard` (privé) | `~/kuuma-dashboard` | Next.js-dashboard (draait op Vercel) |

Beide staan onder de **eraSauna** GitHub-organisatie. De scraper draait op GitHub Actions
(niet op Vercel). Het dashboard draait op Vercel (niet op GitHub Actions).

---

## 4. Accounts & waar de secrets staan

| Dienst | Account | Waarvoor | Kosten |
|---|---|---|---|
| GitHub | org **eraSauna** | code + Actions | gratis |
| IPRoyal (proxy) | **theovanjacobus@gmail.com** | residentieel IP, `geo.iproyal.com:12321` | ~$6/GB, pay-as-you-go |
| Supabase | **flipjacobs98@gmail.com**, project ref `bconnqofjbqasjleuzen` | database | gratis (free tier) |
| Vercel | **eraSauna**, project `srapey` | dashboard-hosting | gratis (Hobby) |
| Healthchecks.io | **info@erasauna.nl** | storingsmail | gratis |

**GitHub Secrets** (in `eraSauna/Scrapey` → Settings → Secrets → Actions):
- `PROXY_URL` = `http://GEBRUIKER:WACHTWOORD@geo.iproyal.com:12321` (uit IPRoyal)
- `SUPABASE_URL` = `https://bconnqofjbqasjleuzen.supabase.co`
- `SUPABASE_KEY` = de **secret/service** key van Supabase (nooit de anon key)
- `HC_PING_URL` = de ping-URL van de healthchecks-check

**Vercel env vars** (in het `srapey`-project → Settings → Environment Variables):
- `SUPABASE_URL`, `SUPABASE_KEY` (zelfde als boven), `DASHBOARD_PASSWORD` (wachtwoord voor het dashboard)

> Pushen naar GitHub gaat via HTTPS met een **Personal Access Token** (scopes: `repo` + `workflow`),
> aangemaakt onder het eraSauna-account. De token zit niet in de repo.

---

## 5. Hoe de scrapers werken

### Kuuma — `periode.py` + `.github/workflows/scrape.yml`
- Haalt bij elke run eerst de actuele publieke nonce van een Kuuma-boekingspagina.
- Vraagt daarna via `periode_get_day` alle actieve sauna's en drop-in-slots in één JSON-call op.
- Capaciteit, prijs en beschikbaarheid komen live mee; `reserveringen = capaciteit − beschikbaar`.
- `locations.py` bewaart alleen de stabiele koppeling voor historische keys. Nieuwe actieve
  sauna's krijgen automatisch een key en worden vóór hun metingen in Supabase ge-upsert.
- Actief bij migratie: de 9 bestaande locaties plus **Amsterdam Aan 't IJ**. Periode kent ook
  Wijk aan Zee en Scheveningen, maar die worden pas toegevoegd zodra ze boekbare sauna-slots hebben.
- **2 runs/dag** (Amsterdam): **04:00 (ochtend)** meet de hele dag en legt de vooraf-stand vast
  (`beschikbaar_ochtend`); **15:00 (middag)** werkt de nog-open slots bij.
- **Robuustheid:** drie begrensde HTTP-pogingen en harde validatie op datum, capaciteit,
  beschikbaarheid, dubbele slots en lege responses.
- **Meetmoment (`RUN_LABEL`)** wordt bepaald op **wélke cron** de run triggerde (`github.event.schedule`),
  niet op de klok — zo verschuift een late cron-start het label niet. Alleen `ochtend` legt de
  vooraf-stand vast.
- **Datazuinig:** geen browserinstallatie, screenshots of proxyverkeer; normale run duurt seconden.

### Saunaboot — `boot.py` + `.github/workflows/boot.yml`
- **1 pagina:** `https://www.desaunaboot.nl/boeken` (Wix-site met Bookeo-widget).
- Leest **alleen de getoonde (huidige) vaardag** — geen dagen vooruit.
- Per tijdslot: **"Beschikbaar: 8" = vrij**, **WACHTLIJST (of < 8) = geboekt** (privéboot = hele boot).
- **Omzet-schatting:** aantal personen is niet zichtbaar, dus per geboekt slot wordt **3–6 personen**
  aangenomen (deterministisch per slot, dus stabiel) en de prijs uit de staffel berekend
  (doordeweeks/weekend). Zie `LADDER` in `boot.py`.
- **1 run/dag: 04:00 (ochtend)**. Via upsert eindigt elke vaardag met zijn dag-zelf-waarde.

### Belangrijke details
- Kuuma-env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `TARGET_DATE`, `RUN_LABEL` en optioneel `ONLY`.
- Billies/Boot draaien nog **headed via xvfb** en gebruiken daarnaast `PROXY_URL` en `DEBUG`.

---

## 6. Supabase-schema

Draai de SQL in de Supabase **SQL Editor** (kies "Run and enable RLS" bij nieuwe tabellen).
- `schema.sql` — Kuuma: tabel `locaties` (seed), tabel `slot_beschikbaarheid`, views
  `bezetting_dag`, `bezetting_totaal`, `bezetting_locatie_totaal`, `bezetting_per_slot`,
  `bezetting_maand`, `bezetting_maand_totaal`.
- `boot_schema.sql` — Boot: tabel `boot_beschikbaarheid`, views `boot_dag`, `boot_slot`.

RLS staat **aan** op de tabellen; de views hebben `security_invoker = on`. De scraper en het
dashboard gebruiken de **secret key** (omzeilt RLS); de anon key kan niets lezen. Data is dus niet
publiek leesbaar.

**Kernbegrip Kuuma:** invoer = *beschikbaar* (wat de site toont). `reserveringen = max − beschikbaar`.
`slot_beschikbaarheid` houdt één rij per (locatie, datum, slot); de middagrun overschrijft alleen
`beschikbaar` (niet `beschikbaar_ochtend`).

---

## 7. Dashboard (Next.js, Vercel)

App Router, **server components** die Supabase server-side lezen met de secret key. Wachtwoord via
`middleware.js` (env `DASHBOARD_PASSWORD`).

| Route | Wat |
|---|---|
| `/` | Kuuma-overzicht: periodefilter (dag/week/maand/3 mnd/alles + losse maanden), sorteerbare ranglijst, vandaag per sauna, drukste dagen, per maand |
| `/locatie/[key]` | Detail per Kuuma-locatie: vandaag per tijdslot (vergelijk met live site), vooraf 04:00 vs definitief, per maand/dag/tijdslot |
| `/analyse` | Dag-van-de-week, weekend vs doordeweeks, weekend-afhankelijkheid, drukste tijden, vaakst uitverkocht, vooraf vs same-day, weektrend |
| `/boot` | Saunaboot: geboekte slots + geschatte omzet, populairste tijdslot, per dag. Schakelaar naar Kuuma bovenaan |

- `app/lib.js` — gedeelde helpers: `sb()` (Supabase-fetch), formatters, sauna-thema (kleuren,
  kiuas-SVG, tonttu-SVG, `SaunaHeader`).
- `app/layout.js` — globale stijl (warm hout-thema, animaties).

Het thema is generiek "sauna"; op `/boot` staat bewust géén Kuuma-merknaam (ander merk).

---

## 8. Hoe je het gebruikt en wijzigt

### Data bekijken
Open het dashboard op Vercel (project `srapey`, bv. `srapey.vercel.app`) en log in met het
`DASHBOARD_PASSWORD`.

### Handmatig een scrape starten
GitHub → repo `eraSauna/Scrapey` → **Actions** → kies "Kuuma bezetting scraper" of
"Saunaboot scraper" → **Run workflow**. (Kost proxy-data, dus spaarzaam.)

### Code wijzigen + pushen
```bash
cd ~/Scrapey            # of ~/kuuma-dashboard
# ... wijzig bestanden ...
git add -A
git commit -m "wat je wijzigde"
git push https://<TOKEN>@github.com/eraSauna/Scrapey.git main   # of kuuma-dashboard.git
```
- **Dashboard** (`kuuma-dashboard`): Vercel deployt automatisch bij elke push naar `main`.
- **Scraper** (`Scrapey`): wijziging geldt bij de eerstvolgende run.
- Test het dashboard lokaal met `npx next build` vóór het pushen.

### Schema wijzigen
Pas `schema.sql` / `boot_schema.sql` aan én draai de gewijzigde SQL in de Supabase SQL Editor
(views zijn `create or replace`; tabellen `if not exists` of via `alter table`).

---

## 9. Onderhoud & veelvoorkomende problemen

| Symptoom | Oorzaak | Oplossing |
|---|---|---|
| Billies/Boot falen op `ERR_TUNNEL_CONNECTION_FAILED`, of proxy geeft **402** | IPRoyal-datategoed op | Log in op IPRoyal → koop data bij |
| Kuuma meldt `periodeData-config niet gevonden` | Kuuma heeft de boekingspagina gewijzigd | inspecteer `periodeData` in de paginabron en pas `periode.py` aan |
| Nieuwe Kuuma-locatie verschijnt | Periode levert voor het eerst actieve slots | wordt automatisch toegevoegd; controleer de `NIEUW`-regel in de log |
| Run faalt volledig | zie logs | je krijgt mail via GitHub én healthchecks |
| "unauthorized IP" in de frame-tekst | proxy-IP door Bookeo geflagd | vers IP (gebeurt automatisch per locatie) |
| Node.js 20 deprecation-warning | GitHub forceert Node 24 op de acties | onschuldig, negeren |
| Cron draait een uur "verkeerd" | zomer-/wintertijd (cron staat in UTC) | in de winter cron 1 uur opschuiven (zie README) |

**Snelle proxy-check (paar KB):**
```bash
curl -sS -m 30 -x "http://USER:PASS_country-nl_session-x_lifetime-5m@geo.iproyal.com:12321" https://ipv4.icanhazip.com -w "\nHTTP=%{http_code}\n"
```
HTTP 200 + een IP = proxy werkt. 402 = tegoed op.

**Storingsmail (healthchecks):** alleen de Kuuma-runs pingen healthchecks (04:00 + 15:00). Zet het
check-schema op cron `0 4,15 * * *` (Europe/Amsterdam) of laat het op "1 day period".

---

## 10. Kosten

Praktisch alleen de **proxy voor Billies/Boot**; Kuuma verbruikt geen proxydata meer.
GitHub Actions, Supabase, Vercel en Healthchecks zitten in gratis tiers.

---

## 11. Bestandsoverzicht (`~/Scrapey`)

| Bestand | Doel |
|---|---|
| `periode.py` | Actieve Kuuma/Periode-scraper (automatische locaties) |
| `scrape.py` | Oude Bookeo-scraper; niet meer actief in de workflow |
| `boot.py` | Saunaboot-scraper (1 pagina) |
| `locations.py` | Stabiele koppeling tussen Periode en historische locatiekeys |
| `test_periode.py` | Parser-, validatie- en Supabase-volgordetests |
| `supa.py` | Supabase-upsert voor Kuuma |
| `schema.sql` / `boot_schema.sql` | Supabase-schema's |
| `requirements.txt` | `playwright` |
| `.github/workflows/scrape.yml` | Kuuma-cron (04:00 + 15:00) |
| `.github/workflows/boot.yml` | Boot-cron (04:00) |
| `README.md` | korte setup |
| `HANDOVER.md` | dit document |

Dashboard (`~/kuuma-dashboard`): `app/page.js`, `app/locatie/[key]/page.js`, `app/analyse/page.js`,
`app/boot/page.js`, `app/lib.js`, `app/layout.js`, `middleware.js`.
