-- Kuuma bezetting — Supabase schema
-- Plak dit in de SQL Editor van je nieuwe (aparte) Supabase-project en run het.

-- Ruwe metingen: één rij per locatie + datum + tijdslot.
create table if not exists public.slot_beschikbaarheid (
    id             bigint generated always as identity primary key,
    location_key   text        not null,
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

-- Dagoverzicht per locatie: reserveringen = max − beschikbaar, plus bezetting en omzet.
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

-- Optioneel: totaal per dag over alle locaties.
create or replace view public.bezetting_totaal as
select
    datum,
    sum(reserveringen) as reserveringen,
    sum(omzet)         as omzet,
    round(avg(bezetting), 3) as gem_bezetting
from public.bezetting_dag
group by datum
order by datum;
