-- Phase 3 (14 Nov 2026): columns for Claude's own-words breakdown and the hands-on answer.
-- Paste this whole file into Supabase > SQL Editor > New query, then click Run.
-- Safe to run again.

alter table public.jobs
  add column if not exists duties      text[],      -- 3-5 bullets, Claude's own words
  add column if not exists looking_for text[],      -- 2-5 bullets, Claude's own words
  add column if not exists key_skills  text[],      -- up to 8
  add column if not exists hands_on    boolean;     -- feeds the fit score (worked out in code)

-- The website may read the new breakdown columns.
grant select (duties, looking_for, key_skills) on public.jobs to anon;

-- Next jobs to tag: past ISB recruiters first, then newest.
create index if not exists jobs_to_tag_idx on public.jobs (past_isb_recruiter desc, posted_at desc nulls last)
  where tagged_at is null and description_trimmed is not null;
