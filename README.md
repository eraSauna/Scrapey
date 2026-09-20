# Kuuma bezetting-scraper

Leest 2× per dag (04:00 en 15:00 Amsterdam) het publieke Kuuma/Periode-overzicht uit —
het aantal **beschikbare plekken** per tijdslot — en schrijft dat naar **Supabase**.
Reserveringen, bezetting % en omzet worden berekend in een SQL-view
(reserveringen = max personen − beschikbaar).

Kuuma gebruikt geen browser of proxy meer: één lichte JSON-call levert alle actieve
sauna's. Capaciteit, prijs en slots komen live mee. Bekende locaties behouden hun
historische database-key; een nieuw actieve Periode-locatie wordt automatisch aan
`locaties` toegevoegd en verschijnt via dezelfde views in het dashboard.

Daarnaast volgt `billies.py` op dezelfde meetmomenten uitsluitend **Big Billies -
Zandvoort**. Morning Mini Steam en The Barrel worden bewust niet meegenomen. De ruwe
metingen staan in `billies_beschikbaarheid`; `billies_dag` en `billies_slot` leveren
de samenvattingen voor de aparte dashboardpagina.

Big Billies en de Saunaboot gebruiken nog wel hun eigen Bookeo/browser-proces en
residentiële proxy. De workflows zijn volledig van elkaar gescheiden.

## Wat jij moet aanmaken

### 1. Residentiële proxy → secret `PROXY_URL` (alleen Billies/Saunaboot)
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
- Voor Big Billies: "Big Billies bezetting scraper" → **Run workflow**.
- Eerste run vult de metingen van vandaag; bekijk ze in Supabase:
  - Tabel `slot_beschikbaarheid` (ruwe metingen)
  - View `bezetting_dag` (reserveringen, bezetting %, omzet per locatie/dag)
  - View `bezetting_totaal` (alles samen per dag)
- Bij problemen laadt de run een artifact `debug/` met de ruwe widget-tekst per locatie.

## Kuuma lokaal testen (geen proxy of packages nodig)
```bash
# zonder SUPABASE_* -> print resultaat als JSON i.p.v. schrijven
ONLY=ams-bjork python3 periode.py
# compacte controle van alle locaties
SUMMARY_ONLY=1 python3 periode.py
# unit-tests
python3 -m unittest -v test_periode.py
```

## Zomer-/wintertijd
Kuuma-cron staat op 02:00 / 13:00 UTC (= 04:00 / 15:00 zomertijd). Het meetmoment-label
(ochtend/middag/avond) wordt bepaald op wélke cron triggerde (`github.event.schedule`), dus een
late start verschuift het label niet. Datum + tijdstempel zijn altijd Amsterdam-tijd. In de winter
schuift het run-moment 1 uur; wil je dat exact houden, zet de crons dan een uur op.

## Healthchecks-schema
Als je in healthchecks een cron-schema gebruikt: `0 4,12,17 * * *`, timezone Europe/Amsterdam,
grace 2 uur (GitHub-cron kan flink later starten — ruime grace voorkomt vals alarm).

## Bestanden
- `periode.py` — actieve Kuuma-scraper (Periode-config, JSON-validatie, nieuwe locaties)
- `scrape.py` — bewaarde oude Bookeo-scraper; wordt niet meer door de workflow gebruikt
- `supa.py` — upsert naar Supabase (alleen stdlib)
- `schema.sql` — tabel + views (eenmalig in Supabase draaien)
- `locations.py` — stabiele koppeling voor bestaande keys + Amsterdam Aan 't IJ
- `.github/workflows/scrape.yml` — de 2×/dag cron
- `billies.py` / `billies_supa.py` — Big Billies-widget en Supabase-upsert
- `billies_schema.sql` — afgeschermde Big Billies-tabel + dashboardviews
- `.github/workflows/billies.yml` — Big Billies ochtend- en middagmeting

## Werking (gevalideerd)
- Periode levert alle actieve Kuuma-sauna's en drop-in-slots in één response.
- De nonce wordt bij iedere run opnieuw van de Kuuma-pagina gelezen en nooit hardcoded.
- Onmogelijke waarden, dubbele slots, een verkeerde datum of lege actieve sauna laten de
  workflow bewust falen; tijdelijke netwerkfouten krijgen drie begrensde pogingen.
- De ochtendrun legt `beschikbaar_ochtend` vast; de middagrun ververst `beschikbaar`
  zonder de ochtendstand te wissen.
