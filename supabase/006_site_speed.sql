-- Make the website fast. Safe to run more than once.
-- The site always reads "live" jobs: tagged, not stale. These indexes cover only those rows.

-- 1. The default list order (best fit, then newest), so the first 50 come straight off the index.
create index if not exists jobs_live_fit_idx
  on public.jobs (fit_score desc, posted_at desc nulls last, id desc)
  where tagged_at is not null and is_stale = false;

create index if not exists jobs_live_new_idx
  on public.jobs (first_seen_at desc)
  where tagged_at is not null and is_stale = false;

-- 2. Search: "contains" matching on title and company.
create extension if not exists pg_trgm with schema extensions;

create index if not exists jobs_live_title_trgm
  on public.jobs using gin (title extensions.gin_trgm_ops)
  where tagged_at is not null and is_stale = false;

create index if not exists jobs_live_company_trgm
  on public.jobs using gin (company extensions.gin_trgm_ops)
  where tagged_at is not null and is_stale = false;

-- 3. Let the site count every function lane in one request (select=function,count())
--    instead of 18. Reads stay limited to the columns granted to anon, and the 3s time limit still applies.
alter role authenticator set pgrst.db_aggregates_enabled = 'true';
notify pgrst, 'reload config';

analyze public.jobs;
