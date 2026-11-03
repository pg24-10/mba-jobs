-- 002: LinkedIn applicant count. Paste into Supabase > SQL Editor > Run.
-- Safe to run more than once.

alter table public.jobs add column if not exists applicants integer;
grant select (applicants) on public.jobs to anon;

create or replace function public.upsert_jobs(rows jsonb)
returns table (id bigint, dedupe_key text, is_new boolean)
language sql
as $$
  insert into public.jobs as j (
    dedupe_key, title, company, company_key, location_city, location_raw, work_mode,
    source_links, sources, source_ids, posted_at, experience_min, experience_max,
    salary_min_lpa, salary_max_lpa, salary_shown, employment_type, is_agency,
    apply_on_company_site, applicants, is_repost, past_isb_recruiter, description_trimmed
  )
  select
    r.dedupe_key, r.title, r.company, r.company_key, r.location_city, r.location_raw, r.work_mode,
    coalesce(r.source_links, '{}'), coalesce(r.sources, '{}'), coalesce(r.source_ids, '{}'),
    r.posted_at, r.experience_min, r.experience_max, r.salary_min_lpa, r.salary_max_lpa,
    coalesce(r.salary_shown, false), r.employment_type, coalesce(r.is_agency, false),
    r.apply_on_company_site, r.applicants, coalesce(r.is_repost, false), coalesce(r.past_isb_recruiter, false),
    r.description_trimmed
  from jsonb_to_recordset(rows) as r(
    dedupe_key text, title text, company text, company_key text, location_city text,
    location_raw text, work_mode text, source_links text[], sources text[], source_ids text[],
    posted_at timestamptz, experience_min numeric, experience_max numeric,
    salary_min_lpa numeric, salary_max_lpa numeric, salary_shown boolean,
    employment_type text, is_agency boolean, apply_on_company_site boolean,
    applicants integer, is_repost boolean, past_isb_recruiter boolean, description_trimmed text
  )
  on conflict on constraint jobs_dedupe_key_key do update set
    source_links   = array(select distinct unnest(j.source_links || excluded.source_links)),
    sources        = array(select distinct unnest(j.sources || excluded.sources)),
    source_ids     = array(select distinct unnest(j.source_ids || excluded.source_ids)),
    last_seen_at   = now(),
    is_stale       = false,
    posted_at      = least(j.posted_at, excluded.posted_at),
    work_mode      = coalesce(j.work_mode, excluded.work_mode),
    experience_min = coalesce(j.experience_min, excluded.experience_min),
    experience_max = coalesce(j.experience_max, excluded.experience_max),
    salary_min_lpa = coalesce(j.salary_min_lpa, excluded.salary_min_lpa),
    salary_max_lpa = coalesce(j.salary_max_lpa, excluded.salary_max_lpa),
    salary_shown   = j.salary_shown or excluded.salary_shown,
    employment_type = coalesce(j.employment_type, excluded.employment_type),
    is_agency      = j.is_agency or excluded.is_agency,
    apply_on_company_site = coalesce(j.apply_on_company_site, excluded.apply_on_company_site),
    applicants     = greatest(j.applicants, excluded.applicants),
    past_isb_recruiter = excluded.past_isb_recruiter,
    description_trimmed = case when j.tagged_at is null
                               then coalesce(j.description_trimmed, excluded.description_trimmed)
                               else j.description_trimmed end
  returning j.id, j.dedupe_key, (xmax = 0) as is_new;
$$;

revoke execute on function public.upsert_jobs(jsonb) from public, anon, authenticated;
