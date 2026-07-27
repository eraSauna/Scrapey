# Kuuma bezetting-scraper

Leest 2× per dag (03:00 en 12:00 Amsterdam) per locatie de Bookeo-widget uit — het
aantal **beschikbare plekken** per tijdslot — en schrijft dat naar **Supabase**.
Reserveringen, bezetting % en omzet worden berekend in een SQL-view
(reserveringen = max personen − beschikbaar).

Draait op GitHub Actions (gratis) via een **residentiële proxy**, omdat Bookeo
datacenter- en geflagde IP's blokkeert.

## Wat jij moet aanmaken

### 1. Residentiële proxy → secret `PROXY_URL`
- Neem een **residentiële** proxy (géén datacenter): bv. IPRoyal, Decodo/Smartproxy, Oxylabs.
- Pay-as-you-go of klein pakket; ons verbruik is ~5–10 MB/dag.
- Vorm: `http://GEBRUIKER:WACHTWOORD@HOST:POORT` (kies NL/EU).

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
Cron staat op 01:00 en 10:00 UTC (= 03:00 en 12:00 zomertijd). Datum + tijdstempel worden
altijd in Amsterdam-tijd bepaald, dus die kloppen jaarrond; alleen het run-moment schuift in
de winter 1 uur. Wil je dat exact houden: in de winter cron op `0 2 * * *` en `0 11 * * *`.

## Bestanden
- `scrape.py` — hoofdscript (proxy, widget uitlezen, media blokkeren om data te sparen)
- `supa.py` — upsert naar Supabase (alleen stdlib)
- `schema.sql` — tabel + views (eenmalig in Supabase draaien)
- `locations.py` — 9 locaties met Bookeo-id's, tijdslots, prijs, capaciteit
- `.github/workflows/scrape.yml` — de 2×/dag cron

## Nog te finaliseren
De tekst-parser voor de slots is getest op de bekende opmaak, maar wordt na de **eerste
echte proxy-run** (met de `debug/`-output) definitief afgesteld op de live DOM.
