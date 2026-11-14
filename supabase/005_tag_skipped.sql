-- Phase 3 (15 Nov 2026): jobs left out of tagging because their title is almost surely fit 1-2.
-- tag-export fills tag_skipped with the reason; such jobs are never sent to Claude.
-- Nothing is deleted: to bring a job back to the tagging queue, set tag_skipped to null.
-- Paste this whole file into Supabase > SQL Editor > New query, then click Run.
-- Safe to run again.

alter table public.jobs
  add column if not exists tag_skipped text;

-- Next jobs to tag (same order as before, now also leaving out skipped and too-thin jobs).
drop index if exists public.jobs_to_tag_idx;
create index if not exists jobs_to_tag_idx on public.jobs (past_isb_recruiter desc, posted_at desc nulls last)
  where tagged_at is null and description_trimmed is not null and not too_thin and tag_skipped is null;
