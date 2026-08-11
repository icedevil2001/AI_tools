-- =============================================================================
-- food_logger -- apply everything to a live Supabase project, in one paste.
--
-- Paste this whole file into the Supabase SQL Editor and run it:
--   https://supabase.com/dashboard/project/<your-project-ref>/sql/new
--
-- The SQL Editor runs as the `postgres` role, which has the privileges these
-- statements need (a trigger on auth.users, policies on storage.objects) and
-- means no database password has to leave your machine.
--
-- Generated from supabase/migrations/. Those numbered files stay authoritative
-- -- this is a convenience bundle, not a replacement, so `supabase db push`
-- still works if you adopt the CLI later.
--
-- Safe to re-run: it is wrapped in a transaction, so any failure rolls the
-- whole thing back rather than leaving a half-created schema. Note it is NOT
-- idempotent -- running it twice on a database that already has the schema
-- will fail on `create schema`/`create table`. That is deliberate: failing
-- loudly beats silently reshaping a schema that already holds real data.
--
-- AFTER running this, two dashboard settings still need changing or the app
-- will not work -- see the end of this file.
-- =============================================================================

begin;

-- ==========================================================================
-- 20260809000001_init_foodlog_schema.sql
-- ==========================================================================

-- Food logger + symptom tracker: core schema.
--
-- Everything lives in a dedicated `foodlog` schema so it cannot collide with
-- anything already present in the Supabase project.

create schema if not exists foodlog;

-- Supabase exposes schemas to PostgREST via the API settings; grant usage so the
-- anon/authenticated roles can reach these objects. RLS below is what actually
-- restricts access -- these grants only make the schema visible.
grant usage on schema foodlog to anon, authenticated;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------

create table foodlog.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  timezone    text        not null default 'UTC',
  created_at  timestamptz not null default now()
);

comment on column foodlog.profiles.timezone is
  'IANA timezone name. Timestamps are stored as timestamptz (absolute instants); '
  'this is only used to render them in the user''s local time.';

-- ---------------------------------------------------------------------------
-- meals
-- ---------------------------------------------------------------------------

create table foodlog.meals (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid        not null references auth.users (id) on delete cascade,
  eaten_at      timestamptz not null,
  photo_path    text,
  portion_size  text,
  notes         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Supports the LAG() window function in foodlog.v_meals and the lateral join in
-- foodlog.v_episodes, both of which order by (user_id, eaten_at).
create index meals_user_eaten_at_idx on foodlog.meals (user_id, eaten_at desc);

comment on column foodlog.meals.photo_path is
  'Storage object path within the private meal-photos bucket, formatted '
  '{user_id}/{meal_id}.jpg. Null for manually entered meals -- a photo is '
  'always optional.';

-- ---------------------------------------------------------------------------
-- ingredients: the canonical dictionary
-- ---------------------------------------------------------------------------

-- This table is the reason any future trend analysis can work. Both the AI
-- extraction path and the manual entry path resolve free text to a row here via
-- normalized_name, so "Chicken", "chicken" and "chicken breast" converge on one
-- id instead of fragmenting into three uncorrelatable strings.
create table foodlog.ingredients (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  normalized_name  text not null unique,
  category         text,
  created_at       timestamptz not null default now()
);

comment on column foodlog.ingredients.name is
  'Human-readable display form, taken from whichever spelling was seen first.';
comment on column foodlog.ingredients.normalized_name is
  'Canonical key produced by lib/ingredients/normalize.ts. The unique '
  'constraint is what makes the upsert idempotent -- do not drop it.';

-- The dictionary is deliberately global rather than per-user: it holds no
-- personal data, only food names, and sharing it means a second user benefits
-- from vocabulary already seen. Access is handled in the RLS migration.

-- ---------------------------------------------------------------------------
-- meal_ingredients
-- ---------------------------------------------------------------------------

create type foodlog.ingredient_source as enum ('ai', 'manual');

create table foodlog.meal_ingredients (
  meal_id        uuid not null references foodlog.meals (id) on delete cascade,
  ingredient_id  uuid not null references foodlog.ingredients (id) on delete restrict,
  source         foodlog.ingredient_source not null,
  confidence     numeric(3, 2),
  quantity_note  text,
  created_at     timestamptz not null default now(),
  primary key (meal_id, ingredient_id)
);

create index meal_ingredients_ingredient_idx
  on foodlog.meal_ingredients (ingredient_id);

alter table foodlog.meal_ingredients
  add constraint meal_ingredients_confidence_range
  check (confidence is null or (confidence >= 0 and confidence <= 1));

-- Confidence is only meaningful for model output. A manually entered ingredient
-- is a statement of fact by the person who ate it, so storing a number there
-- would imply a doubt that does not exist.
alter table foodlog.meal_ingredients
  add constraint meal_ingredients_confidence_ai_only
  check (source = 'ai' or confidence is null);

-- ---------------------------------------------------------------------------
-- episodes
-- ---------------------------------------------------------------------------

create table foodlog.episodes (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid        not null references auth.users (id) on delete cascade,
  started_at  timestamptz not null,
  ended_at    timestamptz,
  symptoms    text[]      not null default '{}',
  severity    smallint,
  notes       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index episodes_user_started_at_idx on foodlog.episodes (user_id, started_at desc);

alter table foodlog.episodes
  add constraint episodes_severity_range
  check (severity is null or (severity between 1 and 10));

alter table foodlog.episodes
  add constraint episodes_ends_after_start
  check (ended_at is null or ended_at >= started_at);

comment on column foodlog.episodes.ended_at is
  'Null means the episode is still ongoing. This lets the episode be logged '
  'while it is happening rather than reconstructed from memory afterwards.';

-- Episodes are intentionally NOT linked to a meal. The person having the
-- episode usually does not know which meal caused it, and making them pick one
-- at log time would bake a guess into the data as though it were an
-- observation. Which meal correlates is an analysis-time question, answered by
-- time window in foodlog.v_episodes.

-- ---------------------------------------------------------------------------
-- ai_extractions: audit of raw model output
-- ---------------------------------------------------------------------------

create table foodlog.ai_extractions (
  id          uuid primary key default gen_random_uuid(),
  meal_id     uuid not null references foodlog.meals (id) on delete cascade,
  model       text not null,
  raw         jsonb not null,
  created_at  timestamptz not null default now()
);

create index ai_extractions_meal_idx on foodlog.ai_extractions (meal_id);

comment on table foodlog.ai_extractions is
  'Unedited model responses, kept so a better model can be re-run over old '
  'photos later and so bad extractions can be debugged -- without needing to '
  're-photograph anything.';

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------

create or replace function foodlog.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger meals_set_updated_at
  before update on foodlog.meals
  for each row execute function foodlog.set_updated_at();

create trigger episodes_set_updated_at
  before update on foodlog.episodes
  for each row execute function foodlog.set_updated_at();

-- ---------------------------------------------------------------------------
-- profile auto-provisioning
-- ---------------------------------------------------------------------------

-- Without this, the first magic-link sign-in produces an auth.users row with no
-- corresponding profile, and every subsequent query joining profiles returns
-- nothing for a user who looks signed in.
create or replace function foodlog.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into foodlog.profiles (id)
  values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function foodlog.handle_new_user();

-- ==========================================================================
-- 20260809000002_rls_policies.sql
-- ==========================================================================

-- Row-level security.
--
-- Enabled in the same deployment as the tables themselves, not bolted on later:
-- an app that works with RLS missing looks identical to one where it is
-- correct, so there is no point at which "add it afterwards" gets noticed.

alter table foodlog.profiles         enable row level security;
alter table foodlog.meals            enable row level security;
alter table foodlog.ingredients      enable row level security;
alter table foodlog.meal_ingredients enable row level security;
alter table foodlog.episodes         enable row level security;
alter table foodlog.ai_extractions   enable row level security;

grant select, insert, update, delete
  on foodlog.profiles, foodlog.meals, foodlog.ingredients,
     foodlog.meal_ingredients, foodlog.episodes, foodlog.ai_extractions
  to authenticated;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------

create policy profiles_select_own on foodlog.profiles
  for select to authenticated
  using (id = (select auth.uid()));

create policy profiles_update_own on foodlog.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- meals
-- ---------------------------------------------------------------------------

-- `using` governs which rows are visible to read/update/delete; `with check`
-- governs what may be written. Both are needed on insert/update, otherwise a
-- user can read only their own rows but write rows owned by someone else.

create policy meals_select_own on foodlog.meals
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy meals_insert_own on foodlog.meals
  for insert to authenticated
  with check (user_id = (select auth.uid()));

create policy meals_update_own on foodlog.meals
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy meals_delete_own on foodlog.meals
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- ingredients (shared dictionary)
-- ---------------------------------------------------------------------------

-- Readable and insertable by any signed-in user. This table holds food names
-- and nothing else -- no user_id, no link to who ate what -- so sharing it
-- leaks nothing while letting the canonical vocabulary accumulate across users.
-- The privacy-bearing link is meal_ingredients, which is locked down below.
--
-- Deliberately no update or delete policy: renaming or removing a canonical
-- ingredient would silently rewrite the meaning of every historical meal that
-- referenced it. Corrections belong at the meal_ingredients level.

create policy ingredients_select_all on foodlog.ingredients
  for select to authenticated
  using (true);

create policy ingredients_insert_any on foodlog.ingredients
  for insert to authenticated
  with check (true);

-- ---------------------------------------------------------------------------
-- meal_ingredients
-- ---------------------------------------------------------------------------

-- Ownership is indirect -- this table has no user_id of its own, so every
-- policy resolves it through the parent meal.

create policy meal_ingredients_select_own on foodlog.meal_ingredients
  for select to authenticated
  using (
    exists (
      select 1 from foodlog.meals m
      where m.id = meal_ingredients.meal_id
        and m.user_id = (select auth.uid())
    )
  );

create policy meal_ingredients_insert_own on foodlog.meal_ingredients
  for insert to authenticated
  with check (
    exists (
      select 1 from foodlog.meals m
      where m.id = meal_ingredients.meal_id
        and m.user_id = (select auth.uid())
    )
  );

create policy meal_ingredients_update_own on foodlog.meal_ingredients
  for update to authenticated
  using (
    exists (
      select 1 from foodlog.meals m
      where m.id = meal_ingredients.meal_id
        and m.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from foodlog.meals m
      where m.id = meal_ingredients.meal_id
        and m.user_id = (select auth.uid())
    )
  );

create policy meal_ingredients_delete_own on foodlog.meal_ingredients
  for delete to authenticated
  using (
    exists (
      select 1 from foodlog.meals m
      where m.id = meal_ingredients.meal_id
        and m.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- episodes
-- ---------------------------------------------------------------------------

create policy episodes_select_own on foodlog.episodes
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy episodes_insert_own on foodlog.episodes
  for insert to authenticated
  with check (user_id = (select auth.uid()));

create policy episodes_update_own on foodlog.episodes
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy episodes_delete_own on foodlog.episodes
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- ai_extractions
-- ---------------------------------------------------------------------------

-- Read-only to the client. Rows are written server-side by the analyze-photo
-- route using the service-role key, which bypasses RLS; there is no legitimate
-- reason for a browser to forge an audit record of what a model returned.

create policy ai_extractions_select_own on foodlog.ai_extractions
  for select to authenticated
  using (
    exists (
      select 1 from foodlog.meals m
      where m.id = ai_extractions.meal_id
        and m.user_id = (select auth.uid())
    )
  );

-- ==========================================================================
-- 20260809000003_timing_views.sql
-- ==========================================================================

-- Derived timing.
--
-- Every interval the app displays is computed here rather than stored as a
-- column. The reason is edits: people log meals late and correct the time
-- afterwards, and the moment that happens, any stored gap downstream of the
-- edited row becomes silently wrong with nothing to flag it. A view recomputes
-- from the underlying timestamps on every read, so the numbers cannot disagree
-- with the data they describe.
--
-- security_invoker = true is load-bearing. Without it a view executes with its
-- OWNER's privileges and bypasses the RLS on the tables underneath -- these two
-- views would then return every user's meal and symptom history to anyone who
-- queried them. It is invisible in single-user testing, which is exactly what
-- makes it dangerous.

-- ---------------------------------------------------------------------------
-- v_meals
-- ---------------------------------------------------------------------------

create view foodlog.v_meals
with (security_invoker = true)
as
select
  m.*,
  lag(m.eaten_at) over w as previous_meal_at,
  case
    when lag(m.eaten_at) over w is null then null
    else round(extract(epoch from (m.eaten_at - lag(m.eaten_at) over w)) / 60.0)::int
  end as minutes_since_previous_meal
from foodlog.meals m
window w as (partition by m.user_id order by m.eaten_at);

comment on view foodlog.v_meals is
  'Meals with the gap to the preceding meal. minutes_since_previous_meal is '
  'null for the first meal ever logged -- render that as "--", not as zero.';

-- ---------------------------------------------------------------------------
-- v_episodes
-- ---------------------------------------------------------------------------

create view foodlog.v_episodes
with (security_invoker = true)
as
select
  e.*,
  -- Null while the episode is ongoing. Deliberately not now() - started_at:
  -- a running clock would make the value change on every read and turn a
  -- half-finished record into what looks like a completed measurement.
  case
    when e.ended_at is null then null
    else round(extract(epoch from (e.ended_at - e.started_at)) / 60.0)::int
  end as duration_minutes,
  e.ended_at is null as is_ongoing,
  lag(e.started_at) over w as previous_episode_at,
  case
    when lag(e.started_at) over w is null then null
    else round(extract(epoch from (e.started_at - lag(e.started_at) over w)) / 60.0)::int
  end as minutes_since_previous_episode,
  last_meal.eaten_at as last_meal_at,
  case
    when last_meal.eaten_at is null then null
    else round(extract(epoch from (e.started_at - last_meal.eaten_at)) / 60.0)::int
  end as minutes_since_last_meal
from foodlog.episodes e
left join lateral (
  select m.eaten_at
  from foodlog.meals m
  where m.user_id = e.user_id
    and m.eaten_at <= e.started_at
  order by m.eaten_at desc
  limit 1
) as last_meal on true
window w as (partition by e.user_id order by e.started_at);

comment on view foodlog.v_episodes is
  'Episodes with duration, gap to the previous episode, and time since the '
  'most recent preceding meal. minutes_since_last_meal is the postprandial '
  'latency -- 15 minutes after eating and 2 hours after eating point at very '
  'different explanations, and it costs nothing to collect because it falls '
  'out of timestamps already being entered. It is NOT a claim that the meal '
  'caused the episode.';

-- Caveat that belongs with the data, not just the docs: these gaps are only as
-- good as the logging. A skipped meal inflates the next
-- minutes_since_previous_meal and nothing here can detect that. Do not present
-- derived gaps to a clinician as though they were measured.

grant select on foodlog.v_meals, foodlog.v_episodes to authenticated;

-- ==========================================================================
-- 20260809000004_storage_meal_photos.sql
-- ==========================================================================

-- Private storage bucket for meal photos.
--
-- Paths are {user_id}/{meal_id}.jpg. The first path segment carries ownership,
-- which is what every policy below checks. Photos are read through short-lived
-- signed URLs generated server-side -- the bucket is never public, because a
-- public bucket makes every meal photo permanently reachable by anyone who
-- learns or guesses the object path.

insert into storage.buckets (id, name, public)
values ('meal-photos', 'meal-photos', false)
on conflict (id) do nothing;

-- storage.foldername(name) splits the object path on '/', so [1] is the
-- leading {user_id} segment. Comparing it to auth.uid() is what stops a user
-- from writing into, or reading from, another user's prefix.

create policy meal_photos_select_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'meal-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy meal_photos_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'meal-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy meal_photos_update_own on storage.objects
  for update to authenticated
  using (
    bucket_id = 'meal-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'meal-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy meal_photos_delete_own on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'meal-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- =============================================================================
-- Live-project steps that the numbered migrations do not carry
-- =============================================================================

-- Backfill profiles for any account that already exists.
--
-- foodlog.handle_new_user() fires on INSERT to auth.users, so users created
-- before this migration ran have no profile row. They would appear signed in
-- while every query joining profiles returned nothing for them.
insert into foodlog.profiles (id)
select id from auth.users
on conflict (id) do nothing;

commit;

-- Tell PostgREST about the new schema.
--
-- Outside the transaction, because NOTIFY only fires on commit. Without this
-- the API keeps serving a stale schema cache and every request to the new
-- tables returns 404 with nothing indicating why.
notify pgrst, 'reload schema';

-- =============================================================================
-- Still to do, in the dashboard -- the app will not work without these
-- =============================================================================
--
-- 1. Settings -> API -> Exposed schemas: add `foodlog`.
--    PostgREST will not serve these tables until you do. The symptom is a 404
--    on every query, which looks exactly like the migration having failed.
--
-- 2. Authentication -> URL Configuration -> Redirect URLs: add your origins
--    including the callback path, e.g.
--      http://localhost:3000/auth/callback
--      https://<your-deployment>/auth/callback
--    Magic links will not complete without this.
--
-- 3. Copy Settings -> API keys into food_logger/.env.local:
--      NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY,
--      SUPABASE_SERVICE_ROLE_KEY (server-only -- never NEXT_PUBLIC_)
--
-- =============================================================================
-- Verify
-- =============================================================================
--
--   -- expect 6 BASE TABLEs and 2 VIEWs
--   select table_name, table_type from information_schema.tables
--   where table_schema = 'foodlog' order by table_name;
--
--   -- every row must show relrowsecurity = true
--   select relname, relrowsecurity from pg_class c
--   join pg_namespace n on n.oid = c.relnamespace
--   where n.nspname = 'foodlog' and c.relkind = 'r';
--
-- Then run supabase/tests/timing_views.sql, which asserts the derived
-- intervals and rolls itself back.
