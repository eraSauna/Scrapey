-- De Saunaboot (Kortenhoef) — apart schema, volledig los van de Kuuma-tabellen.
-- Plak in de SQL Editor van hetzelfde Supabase-project en run.

-- Ruwe metingen: één rij per datum + tijdslot.
create table if not exists public.boot_beschikbaarheid (
    id           bigint generated always as identity primary key,
    datum        date        not null,
    slot_time    text        not null,       -- bv. "10:00"
    beschikbaar  int,                          -- getoond aantal (8 = vrij); null bij wachtlijst
    wachtlijst   boolean     not null default false,
    geboekt      boolean     not null,         -- true = boot bezet (wachtlijst of < 8 vrij)
    prijs        numeric,                       -- slotprijs (bv. 295 / 335)
    run_label    text,
    scraped_at   timestamptz not null default now(),
    unique (datum, slot_time)
);
create index if not exists idx_boot_datum on public.boot_beschikbaarheid (datum);

-- Dagoverzicht: geboekte slots, bezetting en omzet per dag.
create or replace view public.boot_dag as
select
    datum,
    count(*)                                           as slots,
    count(*) filter (where geboekt)                    as geboekt,
    round(count(*) filter (where geboekt)::numeric
          / nullif(count(*), 0), 3)                    as bezetting,
    coalesce(sum(prijs) filter (where geboekt), 0)     as omzet,
    max(scraped_at)                                    as laatst_bijgewerkt
from public.boot_beschikbaarheid
group by datum
order by datum;

-- Per tijdslot: hoe vaak elk slot (10:00/14:00/18:00) geboekt is.
create or replace view public.boot_slot as
select
    slot_time,
    count(*)                                           as dagen,
    count(*) filter (where geboekt)                    as keer_geboekt,
    round(count(*) filter (where geboekt)::numeric
          / nullif(count(*), 0), 3)                    as aandeel_geboekt,
    round(avg(prijs), 2)                               as gem_prijs
from public.boot_beschikbaarheid
group by slot_time
order by slot_time;

-- Zelfde afscherming als de Kuuma-views.
alter view public.boot_dag  set (security_invoker = on);
alter view public.boot_slot set (security_invoker = on);
