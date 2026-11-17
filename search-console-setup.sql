-- =====================================================================
--  Ziyaan Elite — Google Search stats for the admin page
--  Run once in Supabase → SQL Editor (after supabase-setup.sql).
--  A daily GitHub job copies the numbers from Google Search Console
--  into these tables. Only admins can read them.
-- =====================================================================

-- 1) Totals per day ---------------------------------------------------
create table if not exists public.search_daily (
  day          date primary key,
  clicks       integer not null default 0,
  impressions  integer not null default 0,
  position     real,                       -- average position on Google (1 = top)
  updated_at   timestamptz not null default now()
);

-- 2) Breakdown per day: searches, pages, countries, devices -----------
create table if not exists public.search_terms (
  day          date not null,
  kind         text not null check (kind in ('query','page','country','device')),
  name         text not null check (length(name) <= 300),
  clicks       integer not null default 0,
  impressions  integer not null default 0,
  position     real,
  primary key (day, kind, name)
);
create index if not exists search_terms_kind_day on public.search_terms (kind, day desc);

alter table public.search_daily enable row level security;
alter table public.search_terms enable row level security;
drop policy if exists "Admins read search daily" on public.search_daily;
create policy "Admins read search daily" on public.search_daily for select to authenticated using (public.is_admin());
drop policy if exists "Admins read search terms" on public.search_terms;
create policy "Admins read search terms" on public.search_terms for select to authenticated using (public.is_admin());
revoke insert, update, delete on public.search_daily, public.search_terms from anon, authenticated;

-- 3) Private settings (not reachable from the website) ----------------
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table if not exists private.settings (key text primary key, value text not null);
insert into private.settings (key, value)
  values ('gsc_sync_token', replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''))
  on conflict (key) do nothing;

-- 4) Called by the daily GitHub job (needs the secret sync token) ----
create or replace function public.gsc_ingest(p_token text, p_daily jsonb, p_terms jsonb)
returns json
language plpgsql volatile security definer set search_path = public, private as $$
declare d0 date; d1 date; nd int; nt int;
begin
  if p_token is null or p_token is distinct from (select value from private.settings where key = 'gsc_sync_token') then
    raise exception 'not allowed' using errcode = '42501';
  end if;

  select min((x->>'day')::date), max((x->>'day')::date) into d0, d1 from jsonb_array_elements(coalesce(p_daily, '[]')) x;
  if d0 is null then return json_build_object('daily', 0, 'terms', 0); end if;

  insert into public.search_daily (day, clicks, impressions, position, updated_at)
  select (x->>'day')::date, coalesce((x->>'clicks')::int, 0), coalesce((x->>'impressions')::int, 0), (x->>'position')::real, now()
  from jsonb_array_elements(p_daily) x
  on conflict (day) do update set clicks = excluded.clicks, impressions = excluded.impressions,
                                  position = excluded.position, updated_at = now();
  get diagnostics nd = row_count;

  -- replace the breakdown for the days we received
  delete from public.search_terms where day between d0 and d1;
  insert into public.search_terms (day, kind, name, clicks, impressions, position)
  select (x->>'day')::date, x->>'kind', left(x->>'name', 300), coalesce((x->>'clicks')::int, 0),
         coalesce((x->>'impressions')::int, 0), (x->>'position')::real
  from jsonb_array_elements(coalesce(p_terms, '[]')) x
  where (x->>'day')::date between d0 and d1 and x->>'kind' in ('query','page','country','device') and coalesce(x->>'name','') <> ''
  on conflict (day, kind, name) do update set clicks = excluded.clicks, impressions = excluded.impressions, position = excluded.position;
  get diagnostics nt = row_count;

  insert into private.settings (key, value) values ('gsc_last_sync', now()::text)
    on conflict (key) do update set value = excluded.value;
  return json_build_object('daily', nd, 'terms', nt, 'from', d0, 'to', d1);
end $$;
revoke all on function public.gsc_ingest(text, jsonb, jsonb) from public;
grant execute on function public.gsc_ingest(text, jsonb, jsonb) to anon, authenticated;

-- 5) Summary for the admin page (admins only) -------------------------
create or replace function public.gsc_stats(p_days integer default 28)
returns json
language plpgsql stable security definer set search_path = public, private as $$
declare
  d    integer := greatest(1, least(coalesce(p_days, 28), 480));
  last date;
  t0   date;
  p0   date;
  result json;
begin
  if not coalesce(public.is_admin(), false) then
    raise exception 'not allowed' using errcode = '42501';
  end if;
  select max(day) into last from public.search_daily;
  if last is null then
    return json_build_object('days', d, 'empty', true,
      'last_sync', (select value from private.settings where key = 'gsc_last_sync'));
  end if;
  t0 := last - (d - 1);
  p0 := t0 - d;

  select json_build_object(
    'days', d, 'empty', false, 'from', t0, 'to', last,
    'last_sync', (select value from private.settings where key = 'gsc_last_sync'),
    'clicks',      (select coalesce(sum(clicks), 0) from search_daily where day between t0 and last),
    'impressions', (select coalesce(sum(impressions), 0) from search_daily where day between t0 and last),
    'position',    (select round((sum(position * impressions) / nullif(sum(impressions), 0))::numeric, 1)
                      from search_daily where day between t0 and last),
    'prev_clicks',      (select coalesce(sum(clicks), 0) from search_daily where day >= p0 and day < t0),
    'prev_impressions', (select coalesce(sum(impressions), 0) from search_daily where day >= p0 and day < t0),
    'prev_position',    (select round((sum(position * impressions) / nullif(sum(impressions), 0))::numeric, 1)
                           from search_daily where day >= p0 and day < t0),
    'daily', (
      select json_agg(json_build_object('day', g.day::date, 'clicks', coalesce(s.clicks, 0),
                                        'impressions', coalesce(s.impressions, 0), 'position', s.position) order by g.day)
      from generate_series(t0, last, interval '1 day') g(day)
      left join search_daily s on s.day = g.day::date),
    'queries', (select coalesce(json_agg(t), '[]') from (
        select name, sum(clicks) as clicks, sum(impressions) as impressions,
               round((sum(position * impressions) / nullif(sum(impressions), 0))::numeric, 1) as position
        from search_terms where kind = 'query' and day between t0 and last
        group by name order by sum(clicks) desc, sum(impressions) desc, name limit 25) t),
    'pages', (select coalesce(json_agg(t), '[]') from (
        select name, sum(clicks) as clicks, sum(impressions) as impressions,
               round((sum(position * impressions) / nullif(sum(impressions), 0))::numeric, 1) as position
        from search_terms where kind = 'page' and day between t0 and last
        group by name order by sum(clicks) desc, sum(impressions) desc, name limit 15) t),
    'countries', (select coalesce(json_agg(t), '[]') from (
        select name, sum(clicks) as clicks, sum(impressions) as impressions
        from search_terms where kind = 'country' and day between t0 and last
        group by name order by sum(impressions) desc limit 8) t),
    'devices', (select coalesce(json_agg(t), '[]') from (
        select name, sum(clicks) as clicks, sum(impressions) as impressions
        from search_terms where kind = 'device' and day between t0 and last
        group by name order by sum(impressions) desc) t)
  ) into result;
  return result;
end $$;
revoke all on function public.gsc_stats(integer) from public;
grant execute on function public.gsc_stats(integer) to authenticated;
