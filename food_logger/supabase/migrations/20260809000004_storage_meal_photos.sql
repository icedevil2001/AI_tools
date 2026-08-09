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
