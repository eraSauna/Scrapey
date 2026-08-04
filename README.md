# Kuuma bezetting-scraper

Leest 3× per dag (04:00, 12:00 en 17:00 Amsterdam) per locatie de Bookeo-widget uit — het
aantal **beschikbare plekken** per tijdslot — en schrijft dat naar **Supabase**.
Reserveringen, bezetting % en omzet worden berekend in een SQL-view
(reserveringen = max personen − beschikbaar).

Draait op GitHub Actions (gratis) via een **residentiële proxy** (Bookeo blokkeert
datacenter/geflagde IP's) en in een **headed** browser onder xvfb (Bookeo blokkeert
headless browsers met een "session inactive"-fout).

## Wat jij moet aanmaken

### 1. Residentiële proxy → secret `PROXY_URL`
- Neem een **residentiële** proxy (géén datacenter): bv. IPRoyal.
- Pay-as-you-go of klein pakket; ons verbruik is ~5–10 MB/dag.
- Vorm: `http://GEBRUIKER:WACHTWOORD@HOST:POORT` — de kale creds volstaan.
  Voor IPRoyal voegt de scraper zelf NL-geo + een sticky sessie toe
  (`_country-nl_session-…_lifetime-30m`), nodig omdat de Bookeo-sessie aan één IP hangt.

### 2. Apart (gratis) Supabase-project → secrets `SUPABASE_URL` en `SUPABASE_KEY`
1. Maak een **nieuw, los** Supabase-account/organisatie aan (free tier). Niet je REPP-org.
2. Nieuw project → wacht tot het klaar is.
3. **SQL Editor** → plak de inhoud van `schema.sql` → **Run**. (Maakt de tabel + views.)
4. **Project Settings → API**:
   - `SUPABASE_URL` = de Project URL (`https://xxxx.supabase.co`)
   - `SUPABASE_KEY` = de **service_role** key (secret; niet de anon key — die mag niet schrijven met RLS aan).

> De service_role-key omzeilt RLS en mag dus schrijven. Bewaar 'm alleen als GitHub-secret,
> zet 'm nooit in de code of in een publieke repo.

### 3. Persoonlijke (niet-REPP) GitHub-repo
- **Private** repo onder je eigen account; zet de inhoud van deze map erin.
- **Settings → Secrets and variables → Actions → New repository secret**:
  - `PROXY_URL`
  - `HC_PING_URL` (optioneel) = healthchecks.io ping-URL voor storingsmail; leeg = uit
  - `SUPABASE_URL`
  - `SUPABASE_KEY`

## Starten en testen
- **Actions**-tab → "Kuuma bezetting scraper" → **Run workflow** (handmatig).
- Eerste run vult de metingen van vandaag; bekijk ze in Supabase:
  - Tabel `slot_beschikbaarheid` (ruwe metingen)
  - View `bezetting_dag` (reserveringen, bezetting %, omzet per locatie/dag)
  - View `bezetting_totaal` (alles samen per dag)
- Bij problemen laadt de run een artifact `debug/` met de ruwe widget-tekst per locatie.

## Lokaal testen (op je laptop, met proxy)
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m playwright install chromium
# zonder SUPABASE_* -> print resultaat als JSON i.p.v. schrijven
PROXY_URL="http://user:pass@host:poort" DEBUG=1 ONLY=ams-bjork ./venv/bin/python scrape.py
```

## Zomer-/wintertijd
Cron staat op 02:00 / 10:00 / 15:00 UTC (= 04:00 / 12:00 / 17:00 zomertijd). Het meetmoment-label
(ochtend/middag/avond) wordt bepaald op wélke cron triggerde (`github.event.schedule`), dus een
late start verschuift het label niet. Datum + tijdstempel zijn altijd Amsterdam-tijd. In de winter
schuift het run-moment 1 uur; wil je dat exact houden, zet de crons dan een uur op.

## Healthchecks-schema
Als je in healthchecks een cron-schema gebruikt: `0 4,12,17 * * *`, timezone Europe/Amsterdam,
grace 2 uur (GitHub-cron kan flink later starten — ruime grace voorkomt vals alarm).

## Bestanden
- `scrape.py` — hoofdscript (proxy, widget uitlezen, media blokkeren om data te sparen)
- `supa.py` — upsert naar Supabase (alleen stdlib)
- `schema.sql` — tabel + views (eenmalig in Supabase draaien)
- `locations.py` — 9 locaties met Bookeo-id's, tijdslots, prijs, capaciteit
- `.github/workflows/scrape.yml` — de 2×/dag cron

## Werking (gevalideerd)
- Getest via een NL residentiële proxy: alle 3 de Bookeo-accounts leveren correcte slots.
- Bookeo toont per pagina de **huidige dag**; de 03:00-run vangt de volledige dag, de
  12:00-run werkt de nog-open slots bij (upsert overschrijft alleen wat opnieuw gemeten is).
- Per locatie 1 automatische retry bij een transiënte hapering; volgorde en pauzes zijn
  gerandomiseerd (menselijk gedrag).
