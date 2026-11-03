# mba-jobs: Build Brief for Claude Code

Owner: Pranav Gupta (GitHub: pg24-10)
Written: 3 Nov 2026

## How to use this brief

- Read this whole file before writing any code.
- Build one phase at a time, in the order under "Build phases". Stop at every **CHECKPOINT** and wait for Pranav to confirm before moving on.
- Pranav is not a full-time developer. When he has to do something himself (create an account, copy a key, click a setting), explain it click by click in plain language.
- Ask before anything that costs money, changes an account setting, or deletes data.
- Never commit secrets (keys, tokens, passwords) to the repo. Use GitHub Secrets, Vercel environment variables and a local `.env` that is git-ignored.

## What we are building

**mba-jobs** collects job postings relevant to MBA students from LinkedIn, Indeed, Naukri, company career pages and IIMjobs. It tags each job with Claude and shows them on a fast website with rich filters.

- One name everywhere: repo `pg24-10/mba-jobs`, Supabase project `mba-jobs`, Vercel project `mba-jobs` (site `mba-jobs.vercel.app`, or the closest variant Vercel offers).
- The site is open to anyone with the link. Signing in is optional and only adds personal features (saved, applied, hidden jobs across devices).
- Running cost target: Rs 0. Everything uses free tiers. Tagging runs on Pranav's Claude subscription, not the Anthropic API.

## Decisions already made (do not change without asking)

| Area | Decision |
|---|---|
| Daily collection | GitHub Actions, once a day at about 1:00 PM IST |
| LinkedIn route | Layer 1: direct from GitHub Actions. Layer 2: Pranav's Mac, via a background checker that runs LinkedIn when it is marked "pending". No Tailscale, no Apify, no paid proxies. |
| Backfill | One-time, last 30 days, all sources, run on Pranav's Mac |
| Database | Supabase (free tier) |
| Website | Next.js on Vercel (Hobby, free, non-commercial) |
| Tagging | Claude Code subagent on Haiku 5.5, after a Haiku vs Sonnet accuracy check |
| Tagging schedule | Claude scheduled tasks at 2:30 PM and 10:00 PM IST |
| ISB labels | Show a "Past ISB recruiter" tag and filter. Do NOT show "Coming to campus" or any cluster/status info. Keep this as a single on/off setting in config. |
| Sign-in (changed 3 Nov 2026, Pranav) | Optional. Supabase Auth with Google sign-in and an email sign-in link (sent through Resend's free tier). Browsing never needs an account. Store only the email and the user's own job marks; a user can delete their account. |
| Content shown | Title, company, location, key facts, Claude's one-line summary, and a link to the original post. Never show full copied job descriptions. |

## Architecture

```
Job sites (LinkedIn, Indeed, Naukri, career pages, IIMjobs)
        |
        v
GitHub Actions, ~1 PM IST  <---->  Pranav's Mac (LinkedIn fallback + one-time backfill)
  collect, filter, dedupe
        |                                   ^
        v                                   |
Supabase database  <---- tags loaded ----  Claude tagging (2:30 PM, 10 PM IST)
        |                                   reads data/inbox, writes data/tags via the repo
        v
Vercel website (mba-jobs) ---> students
```

Why the repo is the handoff point for tagging: Claude's cloud scheduled tasks can reach GitHub but not job sites or Supabase. So the collector writes untagged jobs to `data/inbox/`, the tagging task writes results to `data/tags/`, and a GitHub Action loads the tags into Supabase.

## Reference files (in `reference/`)

Pranav will place these in the project folder:

| File | Use |
|---|---|
| `PGP - Final Placements - Company Lineup...xlsx` | 234 companies across three sheets (Cluster 1, 2, 3). Headers on row 4: Sr No, Company Name, Industry, Status, Co'26 Role Group(s), Co'25 Role Group(s). Use as the company sweep list. Do not show cluster or status on the site. |
| `ISB_Recruiter_Names.xlsx` | 2,535 past recruiter names (columns: Serial Number, Recruiter Name). Powers the "Past ISB recruiter" tag via fuzzy name matching. |
| `campus_roles_1.txt`, `campus_roles_2.txt` | 125 real campus roles (tab-separated; company in column 2, title in column 3, industry in column 4, min/max experience further right). Used for the safety test and the coverage check. |

## Repo structure (suggested)

```
mba-jobs/
  collector/            Python: one module per source + shared pipeline
    sources/linkedin.py
    sources/jobspy_sources.py   (Indeed, Naukri)
    sources/ats.py              (Greenhouse, Lever, Ashby, Workday, Oracle)
    sources/careers_site.py     (own careers sites: sitemap + Google Jobs tags)
    sources/iimjobs.py
    pipeline.py         normalize, filter, dedupe, company tags, save
    cli.py              commands: backfill, daily, linkedin, coverage, learn-boards, isb-coverage
  config/
    searches.yaml       search groups and locations (editable without code)
    filters.yaml        exclude words, matched on whole words
    companies_watch.yaml  extra companies to sweep
    settings.yaml       e.g. show_past_isb_recruiter: true
  reference/            the four input files above
  data/inbox/           untagged jobs per day (for Claude)
  data/tags/            tags per day (from Claude)
  tests/                safety test with the 125 campus roles
  web/                  Next.js site
  mac/                  launchd checker + install script
  .claude/agents/job-tagger.md   Haiku subagent definition
  ops/tagging-task-prompt.md     prompt for the Claude scheduled task
  .github/workflows/    daily-collect.yml, load-tags.yml, linkedin-test.yml
```

## Locations

Bangalore, Mumbai, Delhi NCR, Hyderabad, Pune, Chennai, Kolkata, Remote (India).

## Search groups (put in `config/searches.yaml`)

Each group is one search per location: about 25 × 8 = 200 searches.

1. "product manager" OR "associate product manager" OR "product lead" OR "product owner"
2. "program manager" OR "programme manager" OR "project manager" OR "program lead"
3. strategy OR strategist OR "corporate strategy" OR "strategic initiatives"
4. "chief of staff" OR "founder's office" OR "CEO's office" OR "MD office" OR "executive assistant to" OR "EA to chairman"
5. consultant OR "principal consultant" OR "engagement manager" OR "engagement lead"
6. transformation OR "special projects" OR "business excellence"
7. "operations manager" OR "strategy and operations" OR "business operations"
8. "growth manager" OR "growth head" OR "business development manager" OR partnerships
9. "category manager" OR "category head" OR "brand manager" OR "product marketing" OR "marketing manager"
10. "zonal manager" OR "regional sales manager" OR "area sales manager" OR "state head" OR "key account manager"
11. "finance manager" OR "finance business partner" OR "FP&A" OR "business finance" OR "corporate finance"
12. "investment banking" OR "equity research" OR "transaction advisory" OR "due diligence" OR deals
13. "private equity" OR "venture capital" OR "investment associate" OR "investor relations"
14. "business analyst" OR "analytics manager" OR "data science manager" OR "decision science"
15. "general manager" OR "business head" OR "business unit head" OR "P&L"
16. "leadership program" OR "leadership programme" OR "leadership associate" OR "future leaders" OR "emerging leaders" OR "management trainee"
17. "AI strategy" OR "AI product" OR "AI transformation" OR presales
18. "private wealth" OR "client experience" OR "wealth management"
19. "MBA" OR "PGDM"
20. "post MBA" OR "MBA graduate"
21. associate MBA
22. consultant MBA
23. manager MBA
24. analyst MBA
25. director MBA

If a source does not support OR, split that group into single phrases automatically (same coverage, more requests). Phase 0 checks this for LinkedIn.

## Sources

### LinkedIn (our own module)

- Use only LinkedIn's public guest pages. **Never log in, never use cookies, never use the authenticated Voyager API.**
  - Search: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&location=...&start=N`
  - Job detail: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jobId}`
  - Company jobs: check the guest company jobs listing (for the company sweep). Verify the exact URL pattern during Phase 0.
- Time filter: past 24 hours for daily runs (`f_TPR=r86400`), past 30 days for the backfill (`f_TPR=r2592000`), or the catch-up window (see pipeline).
- Known limits: about 10 results per request (verify the `start` step), about 1,000 results per search. The guest search ignores experience-level, workplace and job-type filters, so do that filtering ourselves.
- Pace: 2 to 3 seconds between requests, with random jitter. Never faster than 1.5 seconds. On a 429 or 999, back off (double the wait), and after repeated blocks stop LinkedIn for this run and mark it "pending".
- Fetch the detail page only for jobs that pass the exclude filter.
- Use JobSpy's LinkedIn code as a reference for parsing if helpful (speedyapply/JobSpy, MIT).

### Indeed and Naukri (JobSpy)

- `pip install -U python-jobspy` (Python 3.10+). Indeed with `country_indeed="india"`. Naukri with city names as location.
- Use `hours_old` for the window. Each search caps at about 1,000 results.
- Naukri provides an experience range field directly; keep it.

### Company career pages (Greenhouse, Lever, Ashby, Workday, Oracle, own sites)

- Public, keyless JSON:
  - Greenhouse `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
  - Lever `https://api.lever.co/v0/postings/{slug}?mode=json` (respect a 1 second delay)
  - Ashby `https://api.ashbyhq.com/posting-api/job-board/{name}`
- One-time discovery: for each company in the lineup and the watch list, find whether it has one of these boards and store the token in the `companies` table. Many will not; that is fine.
- Added 3 Nov 2026 (Pranav), to cover the 2,500+ past ISB recruiters:
  - Workday and Oracle Cloud careers pages, through the same public JSON their own pages load. These boards list every job a company has, so only titles that look like the searches (plus `big_board_title_words` in filters.yaml) and jobs in the site's cities are opened.
  - Learning from apply links: Indeed and LinkedIn jobs often link to the company's own careers page. Every run saves any it recognises for tracked companies (lineup, ISB, watch list). `mba-jobs learn-boards` seeds this from 30 days of Indeed.
  - Own careers sites: if the apply link is the company's own site, check once whether robots.txt allows us, the sitemap lists job pages, and the pages carry schema.org `JobPosting` tags (the way Google Jobs reads them). If yes, read it every run (`ats_type` "site"); if not, mark "none" and check again after a month.
  - Skipped: SmartRecruiters (robots.txt disallows everyone except LinkedIn), Eightfold (refuses requests).
- `mba-jobs isb-coverage`: after the backfill, lists past ISB recruiters with and without jobs on the site, gaps first (lineup companies on top), into `data/reports/isb-coverage.csv` (git-ignored).

### IIMjobs

- No good open-source scraper exists. Write a small module. Inspect what the site loads in the browser and use its public JSON if available. Keep the request rate low.

### Company sweep

- Daily: LinkedIn company jobs for the 234 lineup companies plus `companies_watch.yaml`, past-24-hours window (usually one request each).
- Watch list starts with: DSP Mutual Fund, DeltaZen47 Advisors, Philip Morris India, Purplle, Shree Cement, Supreme Sky High.

## Pipeline (same code for backfill, daily and Mac runs)

1. **Catch-up window:** for each source, collect everything since that source's last successful run (normally 24 hours; longer if a run failed). Store last success per source in the `runs` table.
2. **Normalize** every job into one schema (see database).
3. **Exclude filter:** `config/filters.yaml`, whole-word matching only. A job never needs a title match to be kept. Known trap: "intern" must not match "International" or "Internal".
4. **Dedupe:** key = normalized company + normalized title + city. Keep every source link on the one job.
5. **Past ISB recruiter tag:** fuzzy-match the company against `ISB_Recruiter_Names.xlsx` (strip suffixes like Pvt, Ltd, India, LLP). Log low-confidence matches for review rather than guessing.
6. **Save** to Supabase (upsert).
7. **Inbox file:** write the day's untagged jobs to `data/inbox/YYYY-MM-DD-HHMM.json` with the trimmed requirements text, commit and push.
8. **Run log:** jobs found per source, which LinkedIn route worked, errors.

## Database (Supabase)

**jobs**
- id, dedupe_key (unique), title, company, company_key, location_city, work_mode, source_links (array), sources (array), posted_at, first_seen_at, last_seen_at, is_stale
- experience_min, experience_max (from Naukri or Claude), salary_min_lpa, salary_max_lpa, salary_shown, employment_type, is_agency
- past_isb_recruiter (bool)
- description_trimmed (temporary: deleted after tagging)
- Claude tags: function, seniority, background_wanted (array), mba_requirement (required / preferred / not mentioned), masters_mentioned, industry, company_type, startup_stage (nullable, approximate), fit_score (1 to 5), summary (one line, Claude's own words), tagged_at, tag_model

**companies**: name, company_key, in_lineup (bool, not shown on site), in_isb_recruiters (bool), in_watch_list (bool), ats_type, ats_token, linkedin_company_id

**runs**: run_id, started_at, finished_at, machine (github / mac), source, window_start, jobs_found, jobs_new, linkedin_route (direct / mac / skipped), status, errors

- Row-level security: the website uses a read-only key that can only SELECT jobs. Only the collector's service key can write.
- Mark jobs stale after 30 days or when the posting disappears. Hide stale jobs by default.
- Size target: about 1 KB per job after descriptions are deleted. Stay well under the 500 MB free limit.

## LinkedIn fallback on Pranav's Mac

- When the 1 PM GitHub run gets blocked by LinkedIn, it marks LinkedIn "pending" in `runs`.
- A launchd background job on the Mac runs every 30 minutes while the Mac is awake (and soon after it wakes). It checks for "pending". If found, it runs the LinkedIn module from the Mac using the same pipeline, then clears the flag.
- Also provide a manual command: `mba-jobs linkedin`.
- If LinkedIn pushes back from the Mac too, slow down and stop. Never hammer it. Pranav is often on campus Wi-Fi, so keep the pace gentle.
- Provide `mac/install.sh` that sets this up, and a matching uninstall.

## Backfill (one time, on the Mac)

- Command: `mba-jobs backfill --days 30`. Covers all sources and all search groups.
- **Resumable:** checkpoint after each search, so stopping and restarting continues where it left off.
- Expected time: LinkedIn about 8,000 requests, roughly 6 to 8 hours; other sources about 1 hour. Show progress and an estimated finish time.
- Tell Pranav to run it overnight with the Mac plugged in, using `caffeinate -i` to keep it awake, on a phone hotspot or home Wi-Fi, not campus Wi-Fi. Data use is about 1 GB.

## Tagging with Claude

- Define a subagent in `.claude/agents/job-tagger.md` with `model: haiku`. It takes a batch of 50 jobs and returns JSON tags for each (fields listed under the `jobs` table).
- The main session reads inbox files and hands them to the tagger **one batch at a time, sequentially, never in parallel**. Parallel subagent dispatch has caused hangs in Pranav's other routines.
- Send only the requirements part of each description (trimmed), not the whole text.
- Resumable: a job tagged once is never re-tagged. If a usage limit stops the run, the next run continues.
- **Accuracy check first:** tag the same 50 jobs with Haiku and with Sonnet and show Pranav a comparison per field. If agreement is about 90% or more, use Haiku for everything. If not, use Sonnet for background_wanted and fit_score only.
- **Backfill tagging:** one session, batches of 50, sequential.
- **Daily tagging:** write `ops/tagging-task-prompt.md` for a Claude scheduled task that runs at 2:30 PM and 10:00 PM IST. It clones the repo, tags new inbox files, writes `data/tags/*.json`, commits and pushes. Help Pranav create the scheduled task.
- `load-tags.yml` GitHub Action: on push to `data/tags/`, load the tags into Supabase, then delete description_trimmed for those jobs.

## GitHub Actions

- `linkedin-test.yml`: manual trigger, for Phase 0.
- `daily-collect.yml`: about 1 PM IST. Cron is UTC, so use an off-the-hour minute to avoid delays, e.g. `23 7 * * *` (12:53 IST). Also allow manual runs.
- `load-tags.yml`: on push to `data/tags/`.
- GitHub emails Pranav when a workflow fails. Keep that on.

## Website (Next.js on Vercel, `web/`)

- **Main page:** search bar, filter panel, and a list of job cards sorted by fit score (option: newest).
- **Job card:** title, company, "Past ISB recruiter" badge (if on), city and work mode, years required, salary if shown, posted date, Claude's one-line summary, Apply button linking to the original post. No full description.
- **Filters:**
  - Function, seniority
  - Years of experience (min-max slider), background wanted, MBA required / preferred / not mentioned, industry experience required
  - Past ISB recruiter
  - Industry, company type, startup stage (marked approximate)
  - City (multi-select), work mode
  - Salary range (LPA) and "salary shown only" (only jobs that list a salary; all sources stored in lakhs a year)
  - Posted within (24 hours / 7 days / 30 days), source, apply on company site vs job board
  - Hide recruitment agencies and reposts, full-time vs contract
- **Personal features:** save (bookmark), hide, mark applied, "new since your last visit". Signed out: kept in the browser (localStorage, with try/catch). Signed in: kept in a `user_jobs` table (user_id, job_id, saved / applied / hidden, time) that each user can only read and change for themselves (row-level security `auth.uid() = user_id`); browser marks are copied up on first sign-in.
- **Sign-in:** a small "Sign in" button (Google, or email link). Account menu with "Delete my account". A short plain privacy note.
- **Shareable searches:** the current filters and sort live in the page address, so copying the link opens the same results.
- "Show all" toggle that includes low fit scores. Stale jobs hidden by default.
- A small "Last updated: <time>" line from the latest successful run.
- Must work well on a phone. Fast first load. Read-only Supabase key only.
- Plain, simple wording in the UI.

## Safety test and coverage check

- `tests/test_campus_roles.py`: loads the 125 campus roles and asserts the exclude filter keeps **all 125**. Runs on every change (locally and in GitHub Actions). A change that drops any of them fails.
- `mba-jobs coverage`: after the backfill (and whenever Pranav adds a new campus list), searches the database for each campus role by company and similar title, and reports found / not found with a hit rate. Use the misses to improve search groups or the watch list.

## Secrets

| Secret | Where it goes | Used by |
|---|---|---|
| SUPABASE_URL | GitHub Secrets, Mac `.env`, Vercel | All |
| SUPABASE_SERVICE_KEY (write) | GitHub Secrets, Mac `.env` only | Collector, load-tags |
| SUPABASE_ANON_KEY (read-only) | Vercel environment variables | Website |
| Google OAuth client ID and secret | Supabase dashboard (Auth > Providers) only | Sign-in |
| Resend SMTP key | Supabase dashboard (Auth > SMTP) only | Email sign-in links |
| GitHub access for the tagging task | Set up with Pranav when creating the scheduled task | Tagging task |

## Build phases

**Phase 0: LinkedIn test from GitHub (about 10 minutes)**
- Create the private repo `pg24-10/mba-jobs` with `linkedin-test.yml`.
- Run about 10 LinkedIn guest searches from GitHub Actions (e.g. "chief of staff" in Bangalore, "product manager" in Mumbai) with the past-24-hours filter, plus one grouped OR search, plus one job detail fetch.
- Report: status codes, results per search, whether OR is respected, whether the detail page returned a description.
- **CHECKPOINT:** show Pranav the results and say whether layer 1 is viable.

**Phase 1: Repo, database, collector**
- Help Pranav create the Supabase project (click by click), create the tables and security rules, add secrets.
- Build the collector, all source modules, the pipeline and the safety test. Load reference files into `companies`.
- Do a small test run on the Mac (one search group, two cities, past 3 days) and show the results.
- **CHECKPOINT:** Pranav reviews 20 sample jobs in Supabase.

**Phase 2: Backfill**
- Run ATS discovery for lineup and watch list companies.
- Give Pranav the exact backfill command and setup (caffeinate, hotspot). He starts it.
- When done, run the coverage check against the 125 campus roles, and `mba-jobs isb-coverage` for the past ISB recruiters.
- **CHECKPOINT:** report total jobs per source, duplicates removed, and the coverage hit rate.

**Phase 3: Tagging**
- Create the job-tagger subagent. Run the 50-job Haiku vs Sonnet comparison.
- **CHECKPOINT:** Pranav picks the model setup.
- Tag the backfill in one sequential session. Set up `load-tags.yml`.

**Phase 4: Daily automation**
- `daily-collect.yml` on GitHub, the Mac checker (`mac/install.sh`), the `mba-jobs linkedin` command.
- Write `ops/tagging-task-prompt.md` and help Pranav create the 2:30 PM and 10:00 PM scheduled tasks.
- **CHECKPOINT:** one full day runs end to end without Pranav doing anything.

**Phase 5: Website**
- Build the Next.js site, deploy to Vercel as `mba-jobs`, connect the read-only key.
- Add optional sign-in (Google + email link), the `user_jobs` table, and shareable search links. Pranav creates the Google Cloud OAuth client and the Resend account, with click-by-click steps.
- **CHECKPOINT:** Pranav reviews on laptop and phone.

**Phase 6: One week of watching**
- Daily summary from the run log: jobs per source, LinkedIn route, errors, tagging status.
- Re-run the coverage check at the end of the week.
- **CHECKPOINT:** Pranav decides when to share the link.

## Rules while building

- LinkedIn guest pages only. No login, no cookies, no accounts.
- Keep request volumes modest and paced as above.
- Store and show only what the site needs. Delete full descriptions after tagging.
- Keep every setting someone might want to change (searches, locations, exclude words, watch list, ISB tag on/off) in `config/`, not in code.
- When something fails, fail one source, not the whole run.
- Explain things to Pranav in plain, simple language.
