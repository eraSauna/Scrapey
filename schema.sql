-- Kuuma bezetting — Supabase schema (Periode; actieve locaties worden ook automatisch ge-upsert)
-- Plak dit volledig in de SQL Editor van je Supabase-project en run het.

-- 1) Referentietabel: locaties + provider-identiteit + actuele tijdslots.
-- De historische kolomnamen bookeo_* blijven behouden om live migratie te vermijden;
-- bij nieuwe metingen bevatten ze "periode:<location-id>" en het service-id.
create table if not exists public.locaties (
    key           text primary key,
    naam          text    not null,
    slug          text    not null,
    bookeo_a      text    not null,      -- provider + locatie-id (historische kolomnaam)
    bookeo_type   text    not null,      -- service-id (historische kolomnaam)
    maxdrop       int     not null,      -- max personen drop-in
    prijs         numeric not null,
    geopend_tot   date,
    slots         text[]  not null       -- tijdslots ("07:00", ...)
);

insert into public.locaties (key, naam, slug, bookeo_a, bookeo_type, maxdrop, prijs, geopend_tot, slots) values
  ('ams-bjork','Ams Björk','marineterrein-bjork','periode:amsterdam-marineterrein','uDw4a2pDUAyQ3XXonN2o',6,18.5,null,'{07:00,08:30,10:00,11:30,13:00,14:30,16:30,18:00,19:30,21:00,22:30}'),
  ('ams-matsu','Ams Matsu','marineterrein-matsu','periode:amsterdam-marineterrein','G7yzdhmpEiaM1yWCPCc0',8,18.5,null,'{06:30,08:00,09:30,11:00,12:30,14:00,16:00,17:30,19:00,20:30,22:00}'),
  ('ams-noord','Ams Noord','boek-sauna-amsterdam-noord','periode:amsterdam-noord','ZKtSDPE2CNDgrjRi39ZM',6,18.5,null,'{07:00,08:30,10:00,11:30,13:00,15:15,16:45,18:15,19:45,21:15}'),
  ('den-bosch','Den Bosch','kuuma-den-bosch','periode:den-bosch','2KC4CrIgY5Twam05fjEr',6,18.5,null,'{07:00,08:30,10:45,12:15,13:45,15:15,16:45,18:15,19:45,21:15}'),
  ('egmond','Egmond aan Zee','boek-sauna-egmond-aan-zee','periode:egmond-aan-zee','cSiOCBqe8ETkZgvyTmIl',10,18.5,null,'{07:00,08:30,10:30,12:00,13:30,15:00,17:00,18:30,20:00,21:30}'),
  ('kallumaan','Kallumaan','drop-in-kallumaan','periode:kallumaan','TzAhXeq4O9FKYJwZS02s',7,18.5,null,'{07:00,09:15,11:30,13:45,16:00,18:15,20:30}'),
  ('nijmegen-lent','Nijmegen Lent','boek-sauna-nijmegen-lent','periode:nijmegen-lent','JggN0BBfFl24F3WRHeRn',6,18.5,null,'{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30,22:00}'),
  ('nijmegen-nyma','Nijmegen Nyma','nijmegen-nyma','periode:nijmegen-nyma','Bu9WNfv2cyfImPufbULw',7,18.5,null,'{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30}'),
  ('rotterdam-delfshaven','Rotterdam Delfshaven','boek-sauna-rotterdam-delfshaven','periode:rotterdam-delfshaven','Pqc1jrrRSP3gIe1Vxn6R',6,18.5,null,'{07:00,08:30,10:00,11:30,13:00,14:30,16:00,17:30,19:00,20:30,22:00}'),
  ('amsterdam-aan-t-ij','Amsterdam Aan ''t IJ','boek-sauna-amsterdam-aan-t-ij','periode:amsterdam-aan-t-ij','7fC6AcqCG9i1q9sYLExl',6,18.5,null,'{07:00,08:30,10:00,11:30,13:00,15:15,16:45,18:15,19:45,21:15}')
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
    beschikbaar    int         not null,      -- laatste stand die de site toont (0 = vol)
    beschikbaar_ochtend int,                   -- vroege stand (blijft staan; middag overschrijft niet)
    max_capaciteit int         not null,      -- max personen drop-in op moment van meten
    prijs          numeric     not null,
    run_label      text,                       -- "ochtend" / "middag"
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
    max(scraped_at)                                      as laatst_bijgewerkt,
    -- stand zoals gemeten in de ochtend (voornamelijk vooraf geboekt)
    sum(max_capaciteit - coalesce(beschikbaar_ochtend, beschikbaar))                     as reserveringen_ochtend,
    round(sum((max_capaciteit - coalesce(beschikbaar_ochtend, beschikbaar)) * prijs), 2) as omzet_ochtend
from public.slot_beschikbaarheid
group by location_key, locatie, datum;

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
