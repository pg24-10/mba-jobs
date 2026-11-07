# Sorting LinkedIn cards: open or skip

The backfill saves LinkedIn jobs from their search card only. Before any job page
is opened, Claude marks each card in `data/state/triage/to-sort.csv`:

- `decision`: `open` (worth reading the full page) or `skip`
- `reason`: a few words, e.g. "strategy role, mid-level" or "sales executive, too junior"

Only the title, company and city are known at this point. **When unsure, open.**
Opening a job costs one LinkedIn request; skipping a good one hides it from students.

## Open

- Roles an MBA graduate (0-8 years before or after the MBA) would apply to:
  strategy, consulting, product, programme/project management, business/operations
  leadership, chief of staff, founder's office, general management, marketing and
  brand, category, growth, business development at manager level, finance (corporate
  finance, FP&A, investment banking, PE/VC, equity research), analytics leadership,
  HR business partner / talent strategy, supply chain and procurement management.
- Titles with manager, senior manager, associate (at consulting, banks, funds),
  lead, head, principal, director, VP, AVP, "associate director".
- Ambiguous titles at a well-known employer (e.g. "Associate" at a bank, "Analyst"
  at a consulting firm): open.

## Skip

- Clearly junior or non-MBA work: executive, officer, coordinator, assistant, clerk,
  trainee, fresher, intern, telecaller, field sales, store/shift roles, data entry.
- Hands-on technical roles with no management angle: developer, engineer, tester,
  designer, technician (but keep "product manager", "engineering manager" type titles).
- Very senior roles out of reach (CEO, CXO, managing director at a large company)
  unless at a startup or the title also reads as a founder's office role.
- Agency reposts that are obvious duplicates of another card in the same list.

Leave `decision` empty to come back to a card later; `triage-import` ignores it.
