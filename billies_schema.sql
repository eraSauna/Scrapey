-- Big Billies - Zandvoort: actuele stand plus vaste ochtendmeting per tijdslot.
create table if not exists public.billies_beschikbaarheid (
  id bigint generated always as identity primary key,
  datum date not null,
  slot_time text not null,
  beschikbaar integer not null,
  beschikbaar_ochtend integer,
  max_capaciteit integer not null default 6,
  prijs numeric(8,2) not null default 20,
  run_label text,
  scraped_at timestamptz not null default now(),
  constraint billies_datum_slot_unique unique (datum, slot_time),
  constraint billies_beschikbaar_valid check (beschikbaar between 0 and max_capaciteit),
  constraint billies_ochtend_valid check (
    beschikbaar_ochtend is null or beschikbaar_ochtend between 0 and max_capaciteit
  )
);

create index if not exists billies_beschikbaarheid_datum_idx
  on public.billies_beschikbaarheid (datum desc);

alter table public.billies_beschikbaarheid enable row level security;
revoke all on public.billies_beschikbaarheid from anon, authenticated;
grant select, insert, update on public.billies_beschikbaarheid to service_role;
grant usage, select on sequence public.billies_beschikbaarheid_id_seq to service_role;

create or replace view public.billies_dag
with (security_invoker = true)
as
select
  datum,
  count(*)::integer as slots_gemeten,
  sum(max_capaciteit)::integer as capaciteit,
  sum(max_capaciteit - beschikbaar)::integer as reserveringen,
  round(
    100 * sum(max_capaciteit - beschikbaar)::numeric / nullif(sum(max_capaciteit), 0),
    1
  ) as bezetting_pct,
  sum((max_capaciteit - beschikbaar) * prijs) as omzet,
  sum(
    case when beschikbaar_ochtend is null then 0
         else max_capaciteit - beschikbaar_ochtend end
  )::integer as reserveringen_ochtend,
  sum(
    case when beschikbaar_ochtend is null then 0
         else (max_capaciteit - beschikbaar_ochtend) * prijs end
  ) as omzet_ochtend,
  max(scraped_at) as laatst_bijgewerkt
from public.billies_beschikbaarheid
group by datum;

create or replace view public.billies_slot
with (security_invoker = true)
as
select
  slot_time,
  count(*)::integer as dagen_gemeten,
  round(avg(max_capaciteit - beschikbaar), 2) as gem_reserveringen,
  round(
    100 * sum(max_capaciteit - beschikbaar)::numeric / nullif(sum(max_capaciteit), 0),
    1
  ) as gem_bezetting_pct,
  count(*) filter (where beschikbaar = 0)::integer as keer_vol
from public.billies_beschikbaarheid
group by slot_time;

grant select on public.billies_dag, public.billies_slot to service_role;
revoke all on public.billies_dag, public.billies_slot from anon, authenticated;
