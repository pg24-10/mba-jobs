-- 009: faster resume matching. 007 checked every skill against every job one by one, which took
-- about 1.7 seconds and hit the 3-second limit once the page also counted results. Now all skills
-- are joined into one pattern, built once, and each job is checked against it in a single pass.
-- A skill that shows up twice in a job counts twice; the skills part is still capped at 10.

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
             else least(10, 4 * coalesce(regexp_count(lower(array_to_string(j.key_skills, ' | ')), sk.pattern), 0))
        end
    )::integer as match
  from public.jobs j
  -- one pattern for all skills, built once per query (not once per job)
  cross join (
    select string_agg(regexp_replace(lower(trim(s)), '([.*+?^${}()|\[\]\\])', '\\\1', 'g'), '|') as pattern
    from unnest(p_skills) s where trim(s) <> ''
  ) sk
$$;
grant execute on function public.match_jobs(numeric, text[], text[], text[], text[], text[]) to anon, authenticated;
