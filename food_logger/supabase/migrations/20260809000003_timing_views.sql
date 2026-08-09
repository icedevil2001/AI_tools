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
