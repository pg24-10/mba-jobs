-- 010: the /admin dashboard. One function returns every number the page shows.
-- Only people in public.admins may call it. Who is an admin is set by hand in the
-- Supabase SQL editor, never in this public repo:
--   insert into public.admins (user_id) select id from auth.users where email = '<you>';
-- Days are India days (Asia/Kolkata). A daily run starts in the evening IST and is
-- counted on the day it started.

create table if not exists public.admins (
  user_id uuid primary key references auth.users (id) on delete cascade
);
alter table public.admins enable row level security;   -- no policies: not readable through the API
revoke all on public.admins from anon, authenticated;

create or replace function public.admin_dashboard()
returns jsonb
language plpgsql stable security definer
set search_path = public, auth
as $$
declare
  since date := (now() at time zone 'Asia/Kolkata')::date - 13;   -- 14 days, today included
begin
  if not exists (select 1 from public.admins where user_id = auth.uid()) then
    raise exception 'admins only' using errcode = '42501';
  end if;

  return jsonb_build_object(
    'now', now(),

    -- Where every job stands.
    'jobs', (
      select jsonb_build_object(
        'total',     count(*),
        'live',      count(*) filter (where tagged_at is not null and not is_stale and not too_thin),
        'tagged',    count(*) filter (where tagged_at is not null),
        'to_tag',    count(*) filter (where tagged_at is null and description_trimmed is not null
                                        and not too_thin and tag_skipped is null),
        'card_only', count(*) filter (where tagged_at is null and description_trimmed is null
                                        and not too_thin and tag_skipped is null),
        'too_thin',  count(*) filter (where too_thin),
        'skipped',   count(*) filter (where tag_skipped is not null),
        'stale',     count(*) filter (where is_stale)
      ) from public.jobs
    ),

    -- Jobs tagged per day.
    'tagged_by_day', coalesce((
      select jsonb_agg(jsonb_build_object('day', d, 'n', n) order by d)
      from (select (tagged_at at time zone 'Asia/Kolkata')::date d, count(*) n
            from public.jobs
            where tagged_at >= (since::timestamp at time zone 'Asia/Kolkata')
            group by 1) t
    ), '[]'::jsonb),

    -- New jobs per source per day, from the run log (one row per machine).
    'runs_by_day', coalesce((
      select jsonb_agg(jsonb_build_object(
               'day', d, 'source', source, 'machines', machines, 'found', seen, 'new', new_jobs,
               'blocked', blocked, 'failed', failed) order by d, source)
      from (select (started_at at time zone 'Asia/Kolkata')::date d, source,
                   count(*) machines, sum(jobs_found) seen, sum(jobs_new) new_jobs,
                   count(*) filter (where errors ilike '%blocked%') blocked,
                   count(*) filter (where status = 'failed') failed
            from public.runs
            where started_at >= (since::timestamp at time zone 'Asia/Kolkata')
            group by 1, 2) t
    ), '[]'::jsonb),

    -- The latest run of each source: every machine of it that started within 12 h of the last one.
    'latest', coalesce((
      select jsonb_agg(jsonb_build_object(
               'source', source, 'started', started, 'finished', finished, 'machines', machines,
               'running', running, 'blocked', blocked, 'failed', failed, 'found', seen, 'new', new_jobs,
               'error', error) order by source)
      from (select r.source, min(r.started_at) started, max(r.finished_at) finished, count(*) machines,
                   count(*) filter (where r.status = 'running') running,
                   count(*) filter (where r.errors ilike '%blocked%') blocked,
                   count(*) filter (where r.status = 'failed') failed,
                   sum(r.jobs_found) seen, sum(r.jobs_new) new_jobs,
                   left(max(r.errors), 200) error
            from public.runs r
            join (select source, max(started_at) last from public.runs group by source) l
              on l.source = r.source and r.started_at > l.last - interval '12 hours'
            group by r.source) t
    ), '[]'::jsonb),

    -- People who signed in with Google.
    'users', (
      select jsonb_build_object(
        'total',        count(*),
        'new_7d',       count(*) filter (where u.created_at > now() - interval '7 days'),
        'active_7d',    count(*) filter (where u.last_sign_in_at > now() - interval '7 days'),
        'active_1d',    count(*) filter (where u.last_sign_in_at > now() - interval '1 day'),
        'with_profile', (select count(*) from public.user_profiles),
        'saved',        (select count(*) from public.user_jobs where kind = 'saved'),
        'applied',      (select count(*) from public.user_jobs where kind = 'applied'),
        'hidden',       (select count(*) from public.user_jobs where kind = 'hidden')
      ) from auth.users u
    ),

    'signups_by_day', coalesce((
      select jsonb_agg(jsonb_build_object('day', d, 'n', n) order by d)
      from (select (created_at at time zone 'Asia/Kolkata')::date d, count(*) n
            from auth.users
            where created_at >= (since::timestamp at time zone 'Asia/Kolkata')
            group by 1) t
    ), '[]'::jsonb),

    'recent_users', coalesce((
      select jsonb_agg(x order by x->>'joined' desc)
      from (select jsonb_build_object(
                     'email', u.email, 'joined', u.created_at, 'last_seen', u.last_sign_in_at,
                     'resume', exists (select 1 from public.user_profiles p where p.user_id = u.id),
                     'marks', (select count(*) from public.user_jobs j where j.user_id = u.id)) x
            from auth.users u order by u.created_at desc limit 25) t
    ), '[]'::jsonb)
  );
end;
$$;

revoke execute on function public.admin_dashboard() from public, anon;
grant  execute on function public.admin_dashboard() to authenticated;

-- Lets the site show the "Dashboard" menu item to admins only.
create or replace function public.is_admin()
returns boolean
language sql stable security definer
set search_path = public
as $$ select exists (select 1 from public.admins where user_id = auth.uid()) $$;
revoke execute on function public.is_admin() from public, anon;
grant  execute on function public.is_admin() to authenticated;
