-- Verification for the derived timing views.
--
-- Run against a database that has the migrations applied:
--   psql "$DATABASE_URL" -f supabase/tests/timing_views.sql
--
-- Wrapped in a transaction that always rolls back, so it is safe to run against
-- a database with real data in it.

begin;

-- A throwaway user. auth.users is the FK target for meals and episodes.
insert into auth.users (id, email, instance_id, aud, role)
values (
  '00000000-0000-0000-0000-0000000000aa',
  'timing-test@example.invalid',
  '00000000-0000-0000-0000-000000000000',
  'authenticated',
  'authenticated'
)
on conflict (id) do nothing;

-- The sequence from the plan: two meals, then an episode 45 minutes after the
-- second one, lasting 35 minutes.
insert into foodlog.meals (id, user_id, eaten_at) values
  ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000aa', '2026-08-09 09:00:00+00'),
  ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-0000000000aa', '2026-08-09 13:30:00+00');

insert into foodlog.episodes (id, user_id, started_at, ended_at, symptoms, severity) values
  ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-0000000000aa',
   '2026-08-09 14:15:00+00', '2026-08-09 14:50:00+00', array['Brain fog'], 6);

do $$
declare
  v int;
begin
  -- 09:00 -> 13:30 is 270 minutes.
  select minutes_since_previous_meal into v
  from foodlog.v_meals where id = '00000000-0000-0000-0000-000000000002';
  assert v = 270, format('expected minutes_since_previous_meal 270, got %s', v);

  -- The first meal ever has no predecessor: null, NOT zero.
  select minutes_since_previous_meal into v
  from foodlog.v_meals where id = '00000000-0000-0000-0000-000000000001';
  assert v is null, format('expected null for the first meal, got %s', v);

  -- 13:30 -> 14:15 is 45 minutes.
  select minutes_since_last_meal into v
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000011';
  assert v = 45, format('expected minutes_since_last_meal 45, got %s', v);

  -- 14:15 -> 14:50 is 35 minutes.
  select duration_minutes into v
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000011';
  assert v = 35, format('expected duration_minutes 35, got %s', v);

  raise notice 'baseline assertions passed';
end $$;

-- The point of using views rather than stored columns: correcting a meal time
-- must move every derived value that depends on it, with no recalculation step.
update foodlog.meals
set eaten_at = '2026-08-09 12:30:00+00'
where id = '00000000-0000-0000-0000-000000000002';

do $$
declare
  v int;
begin
  -- 09:00 -> 12:30 is now 210 minutes.
  select minutes_since_previous_meal into v
  from foodlog.v_meals where id = '00000000-0000-0000-0000-000000000002';
  assert v = 210, format('expected 210 after edit, got %s', v);

  -- 12:30 -> 14:15 is now 105 minutes.
  select minutes_since_last_meal into v
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000011';
  assert v = 105, format('expected 105 after edit, got %s', v);

  raise notice 'edit-propagation assertions passed';
end $$;

-- An ongoing episode must report null duration, not zero and not a value
-- derived from now() that grows every time the row is read.
insert into foodlog.episodes (id, user_id, started_at, ended_at, symptoms) values
  ('00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-0000000000aa',
   '2026-08-09 18:00:00+00', null, array['Dizzy']);

do $$
declare
  d int;
  ongoing boolean;
  gap int;
begin
  select duration_minutes, is_ongoing into d, ongoing
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000012';
  assert d is null, format('ongoing episode should have null duration, got %s', d);
  assert ongoing, 'ongoing episode should report is_ongoing = true';

  -- 14:15 -> 18:00 is 225 minutes between episode starts.
  select minutes_since_previous_episode into gap
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000012';
  assert gap = 225, format('expected minutes_since_previous_episode 225, got %s', gap);

  raise notice 'ongoing-episode assertions passed';
end $$;

-- An episode with no meal before it has no latency to report.
insert into foodlog.episodes (id, user_id, started_at, symptoms) values
  ('00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-0000000000aa',
   '2026-08-08 06:00:00+00', array['Fatigue']);

do $$
declare
  v int;
begin
  select minutes_since_last_meal into v
  from foodlog.v_episodes where id = '00000000-0000-0000-0000-000000000013';
  assert v is null, format('expected null when no meal precedes the episode, got %s', v);

  raise notice 'no-preceding-meal assertion passed';
end $$;

-- Confirm both views actually carry security_invoker. Without it they run as
-- their owner and bypass RLS entirely -- a full leak of every user's history
-- that is invisible until a second user exists.
do $$
declare
  bad text;
begin
  select string_agg(c.relname, ', ') into bad
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'foodlog'
    and c.relkind = 'v'
    and coalesce(
      (select option_value
       from pg_options_to_table(c.reloptions)
       where option_name = 'security_invoker'),
      'false'
    ) <> 'true';

  assert bad is null, format('views missing security_invoker: %s', bad);
  raise notice 'security_invoker assertion passed';
end $$;

rollback;
