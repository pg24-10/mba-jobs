-- Faster counts for the site's function tabs and "Show N roles".
-- The jobs table holds full descriptions, so counting by reading rows touches ~85 MB.
-- On a cold cache that ran past the 3 s statement limit and the counts came back empty.
-- This index carries every column the filters use, so counts read only the index.
-- "not too_thin" matches the public read policy, which the planner adds to every visitor query.
create index if not exists jobs_live_filter_idx on public.jobs (fit_score, function)
  include (
    id, location_city, work_mode, posted_at, first_seen_at, experience_min, experience_max,
    salary_min_lpa, salary_max_lpa, salary_shown, past_isb_recruiter, seniority, mba_requirement,
    industry, company_type, startup_stage, employment_type, is_agency, is_repost,
    apply_on_company_site, sources, background_wanted
  )
  where tagged_at is not null and is_stale = false and not too_thin;

vacuum (analyze) public.jobs; -- run on its own: keeps reads index-only
