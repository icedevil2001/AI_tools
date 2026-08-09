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
