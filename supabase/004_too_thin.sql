-- Phase 3 (14 Nov 2026): leave out jobs whose post says too little.
-- A job with under 60 words of description is not tagged and not shown on the site
-- (tag-export flags new ones as it goes; the threshold lives in collector/tagging.py).
-- Paste this whole file into Supabase > SQL Editor > New query, then click Run.
-- Safe to run again. Nothing is deleted: the jobs are only flagged.

alter table public.jobs
  add column if not exists too_thin boolean not null default false;

-- Flag the untagged jobs that are too thin now.
update public.jobs set too_thin = true
where tagged_at is null
  and description_trimmed is not null
  and not too_thin
  and coalesce(array_length(regexp_split_to_array(btrim(description_trimmed), '\s+'), 1), 0) < 60;

-- 11 jobs already tagged from the title and company alone (their posts had almost no text).
update public.jobs set too_thin = true
where id in (7965, 11173, 1808, 9074, 11561, 3206, 3276, 1807, 1828, 1123, 4807);

-- The website (anon key) never sees flagged jobs.
drop policy if exists "anyone can read jobs" on public.jobs;
create policy "anyone can read jobs" on public.jobs for select to anon using (not too_thin);
