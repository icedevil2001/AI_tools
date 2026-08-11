# Food & symptom diary

A mobile web app for logging meals — photograph a plate, let a vision model
break it into ingredients, correct what it got wrong — and for logging symptom
episodes alongside them, so that a pattern between the two has a chance of
showing up later.

Built for someone experiencing brain fog and lightheadedness after eating, who
needs a food diary to bring to a doctor's appointment.

**This is a diary, not a diagnostic tool.** It records what happened and when.
The time relationships it shows are correlations; it does not interpret them.

## What v1 does

- Photograph a meal; ingredients are extracted by a vision model and shown as
  **editable chips you confirm before anything is saved**
- Add, correct or remove ingredients by hand — a photo is always optional
- Log a symptom episode with start and end times, symptoms and severity 1–10.
  Leave the end open and close it with one tap when it passes
- See the derived intervals: gap between meals, gap between episodes, episode
  duration, and time from the last meal to symptom onset
- Edit or delete anything afterwards

Deliberately **not** in v1: trend analysis / ML, doctor PDF export, offline
sync, barcode scanning, and structured context fields beyond free-text notes.
The schema is designed so each can be added without a destructive migration.

## Stack

Next.js 15 (App Router) + TypeScript + Tailwind, installable as a PWA.
Supabase for Postgres, Auth (magic link) and photo Storage. Vision via
OpenRouter.

## Setup

### 1. Install

```bash
cd food_logger
npm install
cp .env.example .env.local   # then fill it in
```

### 2. Database

The migrations create a dedicated `foodlog` schema, so they will not collide
with anything already in your Supabase project.

**Easiest — no CLI, no database password:** paste
[`supabase/apply_all.sql`](supabase/apply_all.sql) into the SQL Editor at
`https://supabase.com/dashboard/project/<your-project-ref>/sql/new` and run it.
That is the four migrations concatenated, wrapped in a transaction, plus two
things only needed against a live project: a `notify pgrst, 'reload schema'` so
PostgREST picks up the new schema, and a profile backfill for any account that
already exists.

**Or with the CLI:**

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

Either way, then go to **Settings → API → Exposed schemas** in the dashboard
and add `foodlog`. PostgREST will not serve the tables until you do, and the
symptom is an unhelpful 404 on every query that looks exactly like the
migration having failed.

### 3. Environment

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key — safe in the browser, RLS constrains it |
| `SUPABASE_SERVICE_ROLE_KEY` | **Server only.** Bypasses RLS |
| `OPENROUTER_API_KEY` | **Server only** |
| `OPENROUTER_VISION_MODEL` | Defaults to `openai/gpt-5.6-luna` |

Never prefix the bottom three with `NEXT_PUBLIC_` — that inlines them into the
browser bundle.

> The default model slug was not verifiable from the machine this was written
> on. If photo analysis returns a 404, that slug is wrong: check
> <https://openrouter.ai/models> and set `OPENROUTER_VISION_MODEL`. No code
> change is needed. `verifyModelSlug()` in `lib/openrouter.ts` checks this and
> produces an error naming the variable.

### 4. Run

```bash
npm run dev
```

## Verifying it works

```bash
npm run test        # ingredient normalization
npm run typecheck
npm run build
```

SQL structure, without needing a database — catches an unbalanced transaction,
a table shipped without RLS, or a view missing `security_invoker`:

```bash
python3 supabase/tests/validate_sql.py
```

Timing views, against a database with the migrations applied (or paste the file
into the SQL Editor):

```bash
psql "$DATABASE_URL" -f supabase/tests/timing_views.sql
```

That script asserts the intervals, then edits a meal time and re-asserts that
the derived values moved on their own — which is the entire reason they are
views rather than stored columns. It also checks both views carry
`security_invoker`, and rolls back everything at the end.

**Test RLS manually with two accounts.** Sign in as one user, note a meal id,
then sign in as another and try to read it. An app with RLS misconfigured
behaves identically to a correct one until a second person uses it, so this is
the check that cannot be skipped.

**Test on a real phone, ideally an iPhone**, not just desktop devtools — HEIC
photos and the camera capture path only show their problems there.

## Troubleshooting first run

**"Your project's URL and Key are required to create a Supabase client!"**
An environment variable is missing or blank. Newer builds replace this with a
message naming the variable; if you still see the Supabase wording, the code is
out of date. Check which values are actually set — this prints names and
lengths, never values:

```bash
grep -v '^#' .env.local | grep -v '^$' | \
  awk -F= '{ v=substr($0, index($0,"=")+1); printf "%-32s %s\n", $1, (length(v)==0 ? "EMPTY" : "set (" length(v) " chars)") }'
```

Copying `.env.example` gives you every key with an *empty* value, which fails
exactly like a missing one. Note also that `.env.local` must sit in
`food_logger/` beside `package.json` — Next.js does not look in the repository
root — and that Next reads environment variables only at startup, so restart
the dev server after editing it.

**404 on every query, though sign-in works.** `foodlog` is not in **Settings →
API → Exposed schemas**, or the migrations have not been applied.

**Magic link opens but never signs you in.** The origin is missing from
**Authentication → URL Configuration → Redirect URLs**; it needs the full
callback path, e.g. `http://localhost:3000/auth/callback`.

**`next: command not found`.** `npm install` has not run in this directory.

## How it is put together

```
app/
  log/            capture -> analyze -> review -> save
  episode/        symptom entry, ongoing-episode state
  history/        timeline, plus edit routes for meals and episodes
  api/analyze-photo/   server-only OpenRouter call
lib/
  ingredients/    normalize.ts + upsert.ts
  supabase/       browser and server clients, types
  image.ts        HEIC handling, resize to max edge 1024
  openrouter.ts   vision client, zod-validated response
supabase/
  migrations/     schema, RLS, timing views, storage
  tests/          timing_views.sql
```

### Three decisions worth knowing about

**Ingredients are canonicalized, never stored as free text.** Everything passes
through `normalizeIngredient` in `lib/ingredients/normalize.ts` and resolves to
a row in `foodlog.ingredients` keyed on `normalized_name`. If "chicken",
"Chicken" and "grilled chicken breast" were stored as three strings, no future
analysis could ever correlate them. The normalizer errs toward *under*-merging:
"sweet potato" stays distinct from "potato", because two rows that should have
been one is a nuisance, while one row that should have been two is an
unrecoverable loss of signal.

**Timing is derived, never stored.** `foodlog.v_meals` and `foodlog.v_episodes`
compute every interval from the underlying timestamps. Storing them as columns
would mean that correcting a meal time — which happens constantly, because
people log late — silently invalidates every gap downstream of it.

**Episodes are not linked to meals.** He usually will not know which meal caused
an episode, and picking one at log time would record a guess as though it were
an observation. `minutes_since_last_meal` expresses the time relationship
without asserting the causal one.

## Deploying

Vercel: point it at the `food_logger` directory, add the environment variables,
deploy.

### Magic links and changing domains

Vercel mints a new hostname for every deployment, which interacts badly with how
Supabase validates redirects. When `emailRedirectTo` does not match an entry in
the Redirect URLs allowlist, Supabase does **not** report an error — it silently
substitutes the project's **Site URL**. The symptom is a sign-in link that
returns you to an old domain, with nothing indicating why.

Two things prevent it:

**Set `NEXT_PUBLIC_SITE_URL` on Vercel's Production environment only.** The app
resolves its public origin through `lib/site-url.ts`, preferring that value, then
Vercel's stable production domain, then the per-deployment hostname, then
`window.location.origin`. Leaving it unset on Preview means preview deployments
sign in against themselves rather than throwing you to production mid-test.

**Add all three Redirect URLs** under **Authentication → URL Configuration**:

```
http://localhost:3000/**
https://<your-production-domain>/**
https://*-<your-team-slug>.vercel.app/**
```

The wildcard is the one that matters long-term — without it, every future
preview deployment reintroduces this bug. Set **Site URL** to your stable
production origin too, since that is the value Supabase falls back to.
