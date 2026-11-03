-- mba-jobs database: tables, security rules and helper functions.
-- Paste this whole file into Supabase > SQL Editor > New query, then click Run.
-- Safe to run again: it only creates what is missing and replaces functions.

-- ---------------------------------------------------------------- tables

create table if not exists public.jobs (
  id                bigint generated always as identity primary key,
  dedupe_key        text not null unique,
  title             text not null,
  company           text not null,
  company_key       text not null,
  location_city     text,
  location_raw      text,
  work_mode         text,                       -- onsite / hybrid / remote
  source_links      text[] not null default '{}',
  sources           text[] not null default '{}',
  source_ids        text[] not null default '{}', -- e.g. linkedin:4486820744 (internal)
  posted_at         timestamptz,
  first_seen_at     timestamptz not null default now(),
  last_seen_at      timestamptz not null default now(),
  is_stale          boolean not null default false,

  experience_min    numeric,
  experience_max    numeric,
  salary_min_lpa    numeric,
  salary_max_lpa    numeric,
  salary_shown      boolean not null default false,
  employment_type   text,
  is_agency         boolean not null default false,
  apply_on_company_site boolean,
  applicants        integer,                    -- LinkedIn count when we fetched the job
  is_repost         boolean not null default false,
  past_isb_recruiter boolean not null default false,

  description_trimmed text,                     -- temporary: deleted after tagging

  -- Claude tags
  function          text,
  seniority         text,
  background_wanted text[],
  mba_requirement   text check (mba_requirement in ('required', 'preferred', 'not mentioned')),
  masters_mentioned boolean,
  industry          text,
  industry_experience_required text,
  company_type      text,
  startup_stage     text,                       -- approximate
  fit_score         smallint check (fit_score between 1 and 5),
  summary           text,
  tagged_at         timestamptz,
  tag_model         text
);

create index if not exists jobs_source_ids_idx on public.jobs using gin (source_ids);
create index if not exists jobs_company_key_idx on public.jobs (company_key);
create index if not exists jobs_posted_at_idx on public.jobs (posted_at desc);
create index if not exists jobs_untagged_idx on public.jobs (id) where tagged_at is null;

create table if not exists public.companies (
  id                  bigint generated always as identity primary key,
  name                text not null,
  company_key         text not null unique,
  in_lineup           boolean not null default false,   -- never shown on the site
  in_isb_recruiters   boolean not null default false,
  in_watch_list       boolean not null default false,
  lineup_industry     text,
  ats_type            text,                             -- greenhouse / lever / ashby / workday / oracle
  ats_token           text,                             -- board name; workday "tenant.wdN|site"; oracle "host|site"
  linkedin_company_id text,
  linkedin_slug       text,
  discovered_at       timestamptz
);

create table if not exists public.runs (
  run_id          uuid primary key default gen_random_uuid(),
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  machine         text not null,            -- github / mac
  source          text not null,            -- linkedin / indeed / naukri / ats / iimjobs / linkedin_companies
  window_start    timestamptz,
  jobs_found      integer default 0,
  jobs_new        integer default 0,
  linkedin_route  text,                     -- direct / mac / skipped
  status          text not null default 'running', -- running / success / failed / pending / partial
  errors          text
);

create index if not exists runs_source_status_idx on public.runs (source, status, finished_at desc);

-- ---------------------------------------------------------------- security
-- The website uses the public (anon) key: it may read jobs, minus internal
-- columns, and nothing else. Only the secret (service) key can write.

alter table public.jobs      enable row level security;
alter table public.companies enable row level security;
alter table public.runs      enable row level security;

revoke all on public.jobs, public.companies, public.runs from anon, authenticated;
grant all on public.jobs, public.companies, public.runs to service_role;

grant select (
  id, title, company, location_city, work_mode, source_links, sources, posted_at,
  first_seen_at, last_seen_at, is_stale, experience_min, experience_max,
  salary_min_lpa, salary_max_lpa, salary_shown, employment_type, is_agency,
  apply_on_company_site, applicants, is_repost, past_isb_recruiter, function, seniority,
  background_wanted, mba_requirement, masters_mentioned, industry,
  industry_experience_required, company_type, startup_stage, fit_score, summary,
  tagged_at
) on public.jobs to anon;

drop policy if exists "anyone can read jobs" on public.jobs;
create policy "anyone can read jobs" on public.jobs for select to anon using (true);

-- ---------------------------------------------------------------- functions

-- Insert or merge a batch of jobs. Keeps every source link, never overwrites
-- Claude's tags, and reports which rows are new.
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

-- Which of these source ids (e.g. linkedin:123) do we already have?
-- Lets the collector skip detail fetches for jobs it has seen before.
create or replace function public.known_source_ids(ids text[])
returns setof text
language sql stable
as $$
  select distinct s
  from public.jobs, unnest(source_ids) as s
  where source_ids && ids and s = any(ids);
$$;

-- Hide jobs older than 30 days or not seen for 30 days.
create or replace function public.mark_stale()
returns integer
language sql
as $$
  with u as (
    update public.jobs set is_stale = true
    where not is_stale
      and (last_seen_at < now() - interval '30 days'
           or posted_at < now() - interval '30 days')
    returning 1
  )
  select count(*)::integer from u;
$$;

-- "Last updated" line on the website.
create or replace function public.last_updated()
returns timestamptz
language sql stable security definer
set search_path = public
as $$
  select max(finished_at) from public.runs where status = 'success';
$$;

revoke execute on function public.upsert_jobs(jsonb)      from public, anon, authenticated;
revoke execute on function public.known_source_ids(text[]) from public, anon, authenticated;
revoke execute on function public.mark_stale()            from public, anon, authenticated;
grant  execute on function public.upsert_jobs(jsonb), public.known_source_ids(text[]),
                           public.mark_stale() to service_role;
revoke execute on function public.last_updated() from public, authenticated;
grant  execute on function public.last_updated() to anon, service_role;
