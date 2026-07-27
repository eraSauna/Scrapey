-- Kuuma bezetting — Supabase schema (alle 9 locaties)
-- Plak dit volledig in de SQL Editor van je Supabase-project en run het.

-- 1) Referentietabel: de locaties (metadata + Bookeo-id's + tijdslots).
create table if not exists public.locaties (
    key           text primary key,
    naam          text    not null,
    slug          text    not null,
    bookeo_a      text    not null,      -- Bookeo-account
    bookeo_type   text    not null,      -- product-id per locatie
    maxdrop       int     not null,      -- max personen drop-in
    prijs         numeric not null,
    geopend_tot   date,
    slots         text[]  not null       -- tijdslots ("07:00", ...)
);

insert into public.locaties (key, naam, slug, bookeo_a, bookeo_type, maxdrop, prijs, geopend_tot, slots) values
  ('ams-bjork','Ams Björk','marineterrein-bjork','3254A3FXXU175D69E71C5','3254PATUWN17B8204191E',6,17.5,'2027-04-30','{07:00,08:30,10:00,11:30,13:00,14:30,16:30,18:00,19:30,21:00,22:30}'),
  ('ams-matsu','Ams Matsu','marineterrein-matsu','3254A3FXXU175D69E71C5','3254X4FRFA191E02B7FD6',8,17.5,'2027-04-30','{06:30,08:00,09:30,11:00,12:30,14:00,16:00,17:30,19:00,20:30,22:00}'),
  ('ams-noord','Ams Noord','boek-sauna-amsterdam-noord','3254A3FXXU175D69E71C5','325467EJPF183698FB466',6,17.5,'2026-12-31','{07:00,08:30,10:00,11:30,13:00,15:15,16:45,18:15,19:45,21:15,22:45}'),
  ('den-bosch','Den Bosch','kuuma-den-bosch','32547XC6XX191747C1FE3','32549FJM9P199F2A9FD38',7,17.5,'2026-12-31','{07:00,08:30,10:45,12:15,13:45,15:15,16:45,18:15,19:45,21:15}'),
  ('egmond','Egmond aan Zee','boek-sauna-egmond-aan-zee','3254EHPF3N198F61DFBD6','3254XHH93619E97C3F863',10,17.5,'2026-12-31','{07:00,08:30,10:30,12:00,13:30,15:00,17:00,18:30,20:00,21:30}'),
  ('kallumaan','Kallumaan','drop-in-kallumaan','3254A3FXXU175D69E71C5','32546LKUKL1878F1D6984',7,15.0,'2026-09-30','{07:00,09:15,11:30,13:45,16:00,18:15,20:30}'),
  ('nijmegen-lent','Nijmegen Lent','boek-sauna-nijmegen-lent','32547XC6XX191747C1FE3','3254MAC9XU19174D5D1AC',6,17.5,'2026-07-31','{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30,22:00}'),
  ('nijmegen-nyma','Nijmegen Nyma','kuuma-nyma','32547XC6XX191747C1FE3','32547WAWX619817809442',7,17.5,'2026-11-01','{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30}'),
  ('rotterdam-delfshaven','Rotterdam Delfshaven','boek-sauna-rotterdam-delfshaven','32547XC6XX191747C1FE3','3254WA9ELT19600DB8361',6,17.5,'2027-04-30','{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30,22:00}')
on conflict (key) do update set
  naam=excluded.naam, slug=excluded.slug, bookeo_a=excluded.bookeo_a, bookeo_type=excluded.bookeo_type,
  maxdrop=excluded.maxdrop, prijs=excluded.prijs, geopend_tot=excluded.geopend_tot, slots=excluded.slots;

-- 2) Ruwe metingen: één rij per locatie + datum + tijdslot (upsert bij 2e run/dag).
create table if not exists public.slot_beschikbaarheid (
    id             bigint generated always as identity primary key,
    location_key   text        not null references public.locaties(key),
    locatie        text        not null,
    datum          date        not null,
    slot_time      text        not null,      -- bv. "07:00"
    beschikbaar    int         not null,      -- wat de site toont (0 = vol)
    max_capaciteit int         not null,      -- max personen drop-in op moment van meten
    prijs          numeric     not null,
    run_label      text,                       -- "03:00" / "12:00"
    scraped_at     timestamptz not null default now(),
    unique (location_key, datum, slot_time)
);

create index if not exists idx_slot_datum on public.slot_beschikbaarheid (datum);
create index if not exists idx_slot_loc   on public.slot_beschikbaarheid (location_key);

-- 3) Dagoverzicht per locatie: reserveringen = max − beschikbaar, plus bezetting en omzet.
create or replace view public.bezetting_dag as
select
    location_key,
    locatie,
    datum,
    count(*)                                             as slots_gemeten,
    sum(max_capaciteit - beschikbaar)                    as reserveringen,
    sum(max_capaciteit)                                  as capaciteit,
    round(
        sum(max_capaciteit - beschikbaar)::numeric
        / nullif(sum(max_capaciteit), 0), 3)             as bezetting,
    round(
        sum((max_capaciteit - beschikbaar) * prijs), 2)  as omzet,
    max(scraped_at)                                      as laatst_bijgewerkt
from public.slot_beschikbaarheid
group by location_key, locatie, datum
order by datum, locatie;

-- 4) Totaal per dag over alle locaties.
create or replace view public.bezetting_totaal as
select
    datum,
    sum(reserveringen)        as reserveringen,
    sum(omzet)                as omzet,
    round(avg(bezetting), 3)  as gem_bezetting
from public.bezetting_dag
group by datum
order by datum;

-- 5) Cumulatief per locatie (voor het dashboard: wat heeft elke sauna gedraaid).
create or replace view public.bezetting_locatie_totaal as
select
    location_key,
    locatie,
    count(distinct datum)                                as dagen_gemeten,
    min(datum)                                           as eerste_dag,
    max(datum)                                           as laatste_dag,
    sum(max_capaciteit - beschikbaar)                    as reserveringen,
    round(sum((max_capaciteit - beschikbaar) * prijs), 2) as omzet,
    round(
        sum(max_capaciteit - beschikbaar)::numeric
        / nullif(sum(max_capaciteit), 0), 3)             as bezetting
from public.slot_beschikbaarheid
group by location_key, locatie;

-- 6) Per locatie + tijdslot (welke slots lopen vol).
create or replace view public.bezetting_per_slot as
select
    location_key,
    locatie,
    slot_time,
    count(distinct datum)                                                 as dagen,
    round(avg(max_capaciteit - beschikbaar), 2)                           as gem_reserveringen,
    round(avg((max_capaciteit - beschikbaar)::numeric
              / nullif(max_capaciteit, 0)), 3)                            as gem_bezetting
from public.slot_beschikbaarheid
group by location_key, locatie, slot_time
order by location_key, slot_time;
