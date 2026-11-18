-- 007: Google sign-in, marks kept per person, resume matching, company websites.

-- 1. Signed-in people read jobs exactly like everyone else.
grant select (
  applicants, apply_on_company_site, background_wanted, company, company_type, duties, employment_type,
  experience_max, experience_min, first_seen_at, fit_score, function, id, industry,
  industry_experience_required, is_agency, is_repost, is_stale, key_skills, last_seen_at, location_city,
  looking_for, masters_mentioned, mba_requirement, past_isb_recruiter, posted_at, salary_max_lpa,
  salary_min_lpa, salary_shown, seniority, source_links, sources, startup_stage, summary, tagged_at, title,
  work_mode
) on public.jobs to authenticated;
-- company_key lets the job page look up the company's website.
grant select (company_key) on public.jobs to anon, authenticated;
drop policy if exists "anyone can read jobs" on public.jobs;
create policy "anyone can read jobs" on public.jobs for select to anon, authenticated using (not too_thin);
grant execute on function public.last_updated() to authenticated;

-- 2. Company websites, filled by hand for the biggest employers (config/company_sites.yaml).
create table if not exists public.company_sites (
  company_key text primary key,
  website text not null check (website ~ '^https://')
);
alter table public.company_sites enable row level security;
drop policy if exists "anyone can read company sites" on public.company_sites;
create policy "anyone can read company sites" on public.company_sites for select to anon, authenticated using (true);
grant select on public.company_sites to anon, authenticated;

-- 3. Saved / applied / hidden, per signed-in person.
create table if not exists public.user_jobs (
  user_id uuid not null references auth.users (id) on delete cascade,
  job_id bigint not null,
  kind text not null check (kind in ('saved', 'applied', 'hidden')),
  at timestamptz not null default now(),
  primary key (user_id, job_id, kind)
);
alter table public.user_jobs enable row level security;
drop policy if exists "own marks" on public.user_jobs;
create policy "own marks" on public.user_jobs for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
grant select, insert, update, delete on public.user_jobs to authenticated;

-- 4. The profile read from a resume. The resume itself never leaves the person's device.
create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  years numeric,
  functions text[] not null default '{}',
  backgrounds text[] not null default '{}',
  industries text[] not null default '{}',
  cities text[] not null default '{}',
  skills text[] not null default '{}',
  updated_at timestamptz not null default now()
);
alter table public.user_profiles enable row level security;
drop policy if exists "own profile" on public.user_profiles;
create policy "own profile" on public.user_profiles for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
grant select, insert, update, delete on public.user_profiles to authenticated;

-- 5. Delete my account: removes the login, and with it the marks and profile above.
create or replace function public.delete_my_account()
returns void language sql security definer set search_path = '' as $$
  delete from auth.users where id = auth.uid();
$$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

-- 6. Jobs with a match score (0-100) for a profile. The profile is passed in, so it works
-- signed in or not. Plain SQL so Postgres folds it into the query: filters and limits still use indexes.
create or replace function public.match_jobs(
  p_years numeric default null,
  p_functions text[] default '{}',
  p_backgrounds text[] default '{}',
  p_industries text[] default '{}',
  p_cities text[] default '{}',
  p_skills text[] default '{}'
)
returns table (
  id bigint, title text, company text, company_key text, location_city text, work_mode text,
  source_links text[], sources text[], posted_at timestamptz, first_seen_at timestamptz,
  is_stale boolean, tagged_at timestamptz, experience_min numeric, experience_max numeric,
  salary_min_lpa numeric, salary_max_lpa numeric, salary_shown boolean, employment_type text,
  is_agency boolean, apply_on_company_site boolean, is_repost boolean, past_isb_recruiter boolean,
  function text, seniority text, background_wanted text[], mba_requirement text, industry text,
  company_type text, startup_stage text, fit_score smallint, summary text, applicants integer,
  duties text[], looking_for text[], key_skills text[], match integer
)
language sql stable as $$
  select j.id, j.title, j.company, j.company_key, j.location_city, j.work_mode,
    j.source_links, j.sources, j.posted_at, j.first_seen_at,
    j.is_stale, j.tagged_at, j.experience_min, j.experience_max,
    j.salary_min_lpa, j.salary_max_lpa, j.salary_shown, j.employment_type,
    j.is_agency, j.apply_on_company_site, j.is_repost, j.past_isb_recruiter,
    j.function, j.seniority, j.background_wanted, j.mba_requirement, j.industry,
    j.company_type, j.startup_stage, j.fit_score, j.summary, j.applicants,
    j.duties, j.looking_for, j.key_skills,
    (
      -- function: 35
      case when cardinality(p_functions) = 0 then 15
           when j.function = any (p_functions) then 35 else 0 end
      -- experience: 20
      + case when p_years is null then 10
             when j.experience_min is null and j.experience_max is null then 14
             when p_years < coalesce(j.experience_min, 0)
               then greatest(0, 20 - 7 * (coalesce(j.experience_min, 0) - p_years))
             when j.experience_max is not null and p_years > j.experience_max
               then greatest(0, 20 - 4 * (p_years - j.experience_max))
             else 20 end
      -- background: 15
      + case when cardinality(p_backgrounds) = 0 then 7
             when j.background_wanted && p_backgrounds then 15
             when j.background_wanted is null or cardinality(j.background_wanted) = 0
               or 'any' = any (j.background_wanted) then 9
             else 0 end
      -- industry: 10
      + case when cardinality(p_industries) = 0 then 5
             when j.industry = any (p_industries) then 10 else 0 end
      -- city: 10
      + case when cardinality(p_cities) = 0 then 5
             when j.location_city = any (p_cities) or j.work_mode = 'remote' then 10 else 0 end
      -- skills: up to 10
      + case when cardinality(p_skills) = 0 then 5
             else least(10, 4 * (
               select count(*) from unnest(p_skills) s
               where lower(array_to_string(j.key_skills, ' | ')) like '%' || lower(s) || '%'))
        end
    )::integer as match
  from public.jobs j
$$;
grant execute on function public.match_jobs(numeric, text[], text[], text[], text[], text[]) to anon, authenticated;
