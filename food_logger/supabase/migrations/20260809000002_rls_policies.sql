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
