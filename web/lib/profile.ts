// Resume matching. The resume is read on the person's device; only the short profile below is kept.
import type { Job } from "./jobs";
import { CITIES, FUNCS, BACKGROUNDS, INDUSTRIES } from "./jobs";

export type Profile = {
  years: number | null;
  functions: string[];
  backgrounds: string[];
  industries: string[];
  cities: string[];
  skills: string[];
  updated_at: string;
};
export const EMPTY_PROFILE: Profile = { years: null, functions: [], backgrounds: [], industries: [], cities: [], skills: [], updated_at: "" };

const KEY = "mbaj:profile";
export function loadProfile(): Profile | null {
  try {
    const o = JSON.parse(localStorage.getItem(KEY) || "null");
    return o ? clean(o) : null;
  } catch {
    return null;
  }
}
export function saveProfile(p: Profile | null) {
  try {
    if (p) localStorage.setItem(KEY, JSON.stringify(p));
    else localStorage.removeItem(KEY);
  } catch {}
}
const strs = (x: unknown, ok?: string[]) =>
  Array.isArray(x) ? x.filter((v): v is string => typeof v === "string" && (!ok || ok.includes(v))).slice(0, 40) : [];
export function clean(o: Record<string, unknown>): Profile {
  const y = Number(o.years);
  return {
    years: o.years == null || o.years === "" || !Number.isFinite(y) ? null : Math.max(0, Math.min(40, y)),
    functions: strs(o.functions, FUNCS.map((f) => f[0])),
    backgrounds: strs(o.backgrounds, BACKGROUNDS.map((b) => b[0])),
    industries: strs(o.industries, INDUSTRIES.map((b) => b[0])),
    cities: strs(o.cities, CITIES),
    skills: strs(o.skills),
    updated_at: typeof o.updated_at === "string" ? o.updated_at : new Date().toISOString(),
  };
}
export const isEmpty = (p: Profile) =>
  p.years == null && !p.functions.length && !p.backgrounds.length && !p.industries.length && !p.cities.length && !p.skills.length;

/* ---------- reading a resume ---------- */
export async function pdfText(file: File): Promise<string> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages: string[] = [];
  for (let i = 1; i <= Math.min(doc.numPages, 8); i++) {
    const c = await (await doc.getPage(i)).getTextContent();
    let line = "";
    const lines: string[] = [];
    for (const it of c.items as { str?: string; hasEOL?: boolean }[]) {
      line += (it.str ?? "") + " ";
      if (it.hasEOL) {
        lines.push(line.trim());
        line = "";
      }
    }
    lines.push(line.trim());
    pages.push(lines.join("\n"));
  }
  return pages.join("\n");
}

// How the reader works:
//  1. The resume is split into sections by its headings (Education, Work experience, Extra-curriculars…).
//  2. Roles, industries and work background come from the work section only, so a case competition
//     or a university name doesn't count as work. Extra-curriculars count for a quarter.
//  3. Each word counts up to twice, so a theme that runs through the resume beats a word said once.
//  4. Degrees (MBA, engineering, CA/CFA) are read from the education section.
// A word ending in * matches any ending ("valuation*" also finds "valuations").
const FN_WORDS: Record<string, string[]> = {
  sales_bd: ["business development", "sales manager", "sales target*", "key account*", "account manager", "account executive", "revenue target*", "channel partner*", "b2b sales", "enterprise sales", "inside sales", "quota"],
  program_management: ["program manager", "programme manager", "project manager", "pmo", "program management", "project management"],
  operations: ["operations manager", "process improvement", "lean", "six sigma", "service delivery", "plant operations", "business operations"],
  consulting: ["consultant", "consulting", "client engagement*", "engagement manager", "client deliverable*"],
  finance: ["financial planning", "fp&a", "budgeting", "forecasting", "financial analysis", "treasury", "accounting", "audit", "controllership", "taxation", "dcf", "valuation*", "financial model*", "fundrais*", "rights issue", "working capital", "ipo", "mis", "cash flow*", "debt", "capital structure"],
  marketing: ["marketing manager", "brand manager", "brand management", "go-to-market", "digital marketing", "consumer insights", "marketing campaign*"],
  product: ["product manager", "product management", "product roadmap", "prd", "product owner", "user research"],
  analytics: ["analytics", "data analysis", "sql", "power bi", "tableau", "dashboard*", "business analyst", "data analyst"],
  hr: ["human resources", "talent acquisition", "recruitment", "hrbp", "learning and development", "compensation"],
  supply_chain: ["supply chain", "supply-chain", "procurement", "logistics", "inventory", "demand planning", "vendor management", "warehous*"],
  general_management: ["general manager", "p&l owner*", "business head", "chief of staff", "founder's office", "founders office", "p&l responsibility"],
  growth: ["growth manager", "growth marketing", "user acquisition", "performance marketing", "a/b test*"],
  strategy: ["strategy", "corporate development", "market entry", "business planning", "business plan*", "turnaround", "operating model", "value creation", "strategic initiative*"],
  banking: ["investment banking", "relationship manager", "corporate banking", "wealth management", "lending", "credit analysis", "credit appraisal", "credit risk"],
  investing: ["private equity", "venture capital", "pe fund", "pipe", "investment analyst", "investment committee", "ic memo*", "ic note*", "term sheet*", "diligence", "buyout*", "pre-ipo", "stake", "series a", "series b", "series c", "series d", "portfolio compan*", "deal*", "deal sourcing", "irr", "moic", "investment evaluation"],
  technology: ["software engineer", "developer", "full stack", "backend", "frontend", "devops", "machine learning engineer"],
};
// Degrees and qualifications, looked for in the education section (or anywhere if there isn't one).
const DEGREES: Record<string, string[]> = {
  mba: ["mba", "pgdm", "pgp", "post graduate programme in management", "post graduate program in management", "master of business administration", "masters of business administration", "indian school of business", "iim"],
  engineering: ["b.tech", "btech", "b.e.", "bachelor of engineering", "bachelor of technology", "iit"],
  ca_finance: ["chartered accountant", "cfa", "acca", "cpa", "ca final", "ca inter"],
};
// Kinds of past jobs, looked for in the work section.
const ROLES: Record<string, string[]> = {
  consulting: ["mckinsey", "boston consulting", "bcg", "bain", "kearney", "accenture strategy", "deloitte", "pwc", "ey", "kpmg", "consultant", "consulting"],
  ca_finance: ["private equity", "pipe", "investment banking", "equity research", "investment analyst", "financial analyst", "fp&a", "audit", "venture capital", "credit analyst", "corporate finance"],
  sales: ["sales manager", "business development", "key account*", "account executive", "sales target*"],
  marketing: ["marketing manager", "brand manager", "brand management"],
  product: ["product manager", "product owner"],
  analytics: ["data analyst", "business analyst", "data scientist"],
  operations: ["operations manager", "plant operations", "business operations"],
  technology: ["software engineer", "developer", "sde", "programmer"],
};
const IND_WORDS: Record<string, string[]> = {
  consulting: ["consulting firm", "advisory firm", "management consulting"],
  technology: ["saas", "software", "it services", "cloud"],
  bfsi: ["bank", "insurance", "nbfc", "financial services"],
  fintech: ["fintech", "digital payments", "cross-border payments", "payments company", "payment gateway*", "upi", "lending platform", "neobank*"],
  investing: ["private equity", "pe fund", "pipe", "venture capital", "asset management", "portfolio compan*", "investment firm", "family office"],
  internet: ["e-commerce", "ecommerce", "marketplace", "consumer internet", "quick commerce", "edtech", "foodtech", "d2c"],
  fmcg: ["fmcg", "consumer goods", "cpg", "hindustan unilever", "procter", "nestle", "itc limited", "dabur", "marico"],
  retail: ["retail*", "stores", "furniture", "apparel"],
  manufacturing: ["manufactur*", "plant", "automotive", "industrial", "defence", "defense", "aerospace", "components"],
  healthcare: ["healthcare", "hospital*", "pharma", "pharmaceutical*", "medtech", "life sciences"],
  energy: ["energy", "oil and gas", "renewable*", "solar", "power sector", "clean-tech", "cleantech"],
  logistics: ["logistics company", "shipping", "freight", "3pl"],
  real_estate: ["real estate", "construction", "infrastructure"],
  telecom_media: ["telecom", "media", "entertainment", "broadcasting"],
  education: ["edtech", "education company", "k-12"],
  public_social: ["government", "public policy", "ngo", "non-profit", "social impact"],
};
// Skills, named the way job posts name them, with the words a resume might use instead.
// (Single letters like "R" are left out: they'd match almost every post.)
const SKILLS: [string, ...string[]][] = [
  ["Excel", "excel", "spreadsheet*"], ["PowerPoint", "powerpoint", "ppt"], ["SQL", "sql"], ["Python", "python"],
  ["Power BI", "power bi"], ["Tableau", "tableau"], ["Looker", "looker"], ["Google Analytics", "google analytics"],
  ["Salesforce", "salesforce"], ["SAP", "sap"], ["Oracle", "oracle"], ["Jira", "jira"], ["Figma", "figma"],
  ["Financial modelling", "financial model*", "modelling", "modeling", "returns model*", "operating model"],
  ["Valuation", "valuation*", "trading comps", "comps"], ["DCF", "dcf"], ["IRR", "irr", "moic"],
  ["Due diligence", "diligence"], ["M&A", "m&a", "acquisition*", "buyout*", "mergers"], ["Term sheet", "term sheet*", "ssha*"],
  ["Fundraising", "fundrais*", "capital raising", "rights issue"], ["Business plan", "business plan*"],
  ["Portfolio management", "portfolio management", "portfolio monitoring", "monitored"], ["Turnaround", "turnaround"],
  ["Working capital", "working capital"], ["P&L", "p&l"], ["Equity research", "equity research"], ["Investment banking", "investment banking"],
  ["Budgeting", "budgeting"], ["Forecasting", "forecasting"], ["FP&A", "fp&a"], ["Credit analysis", "credit analysis"],
  ["Risk management", "risk management"], ["Compliance", "compliance"], ["Negotiation", "negotiat*"],
  ["Market research", "market research", "sector primer*"], ["Go-to-market", "go-to-market", "gtm"], ["Pricing", "pricing"],
  ["Stakeholder management", "stakeholder*"], ["Project management", "project management"], ["Program management", "program management"],
  ["Agile", "agile"], ["Scrum", "scrum"], ["Product roadmap", "product roadmap"], ["A/B testing", "a/b test*"],
  ["User research", "user research"], ["CRM", "crm"], ["Lead generation", "lead generation"], ["Key account management", "key account*"],
  ["Business development", "business development"], ["Partnerships", "partnership*"], ["Digital marketing", "digital marketing"],
  ["SEO", "seo"], ["Performance marketing", "performance marketing"], ["Brand management", "brand management"],
  ["Supply chain", "supply chain", "supply-chain"], ["Procurement", "procurement"], ["Vendor management", "vendor management", "vendor negotiation*"],
  ["Demand planning", "demand planning"], ["Six Sigma", "six sigma"], ["Process improvement", "process improvement"],
  ["Data analysis", "data analysis"], ["Machine learning", "machine learning"], ["Team leadership", "team leadership", "led a team", "managed a team"],
  ["Recruitment", "recruitment", "talent acquisition"], ["Training", "training programme", "training program"],
];

const esc = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pat = (w: string) => (w.endsWith("*") ? `${esc(w.slice(0, -1))}[a-z]*` : esc(w));
const re = (w: string, g = "") => new RegExp(`(?<![a-z])${pat(w.trim())}(?![a-z])`, g);
const has = (t: string, w: string) => re(w).test(t);
const count = (t: string, w: string) => (t.match(re(w, "g")) ?? []).length;
/** How strongly a text points at each key: each word counts up to twice. */
const score = (t: string, words: string[]) => words.reduce((n, w) => n + Math.min(2, count(t, w)), 0);

/** Splits a resume into its sections by heading. Text before the first heading is the "head". */
type Sections = { head: string; edu: string; work: string; other: string; skills: string; found: boolean };
const HEADS: [keyof Sections, RegExp][] = [
  ["edu", /^(education|academic(s| background| qualifications| details)?|qualifications|educational qualifications)$/],
  ["work", /^((work|professional|relevant|industry) experience|experience|employment( history)?|work history|career( history)?|professional background)$/],
  ["skills", /^((key |technical |core )?skills( (&|and) (interests|tools))?|tools|technical proficiency|core competencies)$/],
  ["other", /^(extra.?curricular( activities)?|achievements( (&|and) interests)?|awards( (&|and) achievements)?|interests|hobbies|positions? of responsibility|leadership( (&|and) activities)?|activities|volunteer(ing)?|certifications?|publications|projects|personal (details|information)|additional information|languages)$/],
  ["head", /^(summary|profile|professional summary|about( me)?|objective|career objective)$/],
];
function sections(raw: string): Sections {
  const s: Sections = { head: "", edu: "", work: "", other: "", skills: "", found: false };
  let cur: keyof Sections = "head";
  for (const line of raw.split(/\n/)) {
    const key = line.toLowerCase().replace(/[^a-z& ]+/g, " ").replace(/\s+/g, " ").trim();
    const hit = key.length < 45 ? HEADS.find(([, r]) => r.test(key)) : undefined;
    if (hit) {
      cur = hit[0];
      s.found = true;
      continue;
    }
    (s[cur] as string) += line + "\n";
  }
  return s;
}

const MONS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MON = "(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\\.?";
const YR = "((?:19|20)\\d{2}|['’‘]\\s?\\d{2})"; // 2023, or '23 as in Jul'23
const yr = (s: string) => (/^\d{4}$/.test(s) ? Number(s) : 2000 + Number(s.replace(/\D/g, "")));

/** Years of work, from "N years of experience" or from the date ranges in the work section. */
function years(t: string, skipSchool: boolean): number | null {
  const said = [...t.matchAll(/(\d{1,2}(?:\.\d)?)\+?\s*(?:years|yrs)\s+(?:of\s+)?(?:work\s+|professional\s+|total\s+)?experience/g)].map((m) => Number(m[1]));
  if (said.length) return Math.max(...said.filter((n) => n < 40));
  const now = new Date();
  const ranges: [number, number][] = [];
  const rx = new RegExp(`(?:${MON}\\s*)?${YR}\\s*(?:-|–|—|to)\\s*(?:(present|current|now|till date|date)|(?:${MON}\\s*)?${YR})`, "g");
  // Lines, or sentences when the text was pasted as one paragraph.
  for (const line of t.split(/\n|[.;|•]\s/)) {
    // With no work section to go on, skip school and college lines, which have date ranges too.
    if (skipSchool && /(?<![a-z])(b\.?tech|b\.?e\.|bachelor|master|mba|pgdm|pgp|university|college|school|institute|class x|cgpa|gpa)(?![a-z])/.test(line)) continue;
    for (const m of line.matchAll(rx)) {
      const a = yr(m[2]) + Math.max(0, m[1] ? MONS.indexOf(m[1].slice(0, 3)) : 0) / 12;
      const b = m[3] ? now.getFullYear() + now.getMonth() / 12 : yr(m[5]) + Math.max(0, m[4] ? MONS.indexOf(m[4].slice(0, 3)) : 11) / 12;
      if (b > a && b - a < 30) ranges.push([a, b]);
    }
  }
  if (!ranges.length) return null;
  ranges.sort((x, y) => x[0] - y[0]);
  let total = 0, [s, e] = ranges[0];
  for (const [a, b] of ranges.slice(1)) {
    if (a <= e) e = Math.max(e, b);
    else {
      total += e - s;
      [s, e] = [a, b];
    }
  }
  total += e - s;
  return Math.round(total * 2) / 2;
}

/** The keys that score best, keeping only those at least `share` of the best one. */
function top(texts: [string, number][], words: Record<string, string[]>, max: number, share: number, min = 1) {
  const scored = Object.entries(words)
    .map(([k, w]) => [k, texts.reduce((n, [t, wt]) => n + wt * score(t, w), 0)] as const)
    .filter(([, n]) => n >= min)
    .sort((a, b) => b[1] - a[1]);
  const best = scored[0]?.[1] ?? 0;
  return scored.filter(([, n]) => n >= best * share).slice(0, max).map(([k]) => k);
}

export function readResume(raw: string): Profile {
  const norm = (x: string) => " " + x.toLowerCase().replace(/[ \t]+/g, " ") + " ";
  const s = sections(raw);
  const all = norm(raw);
  // When no work heading was found (pasted text, odd layouts), read everything as work.
  const work = s.found && s.work.trim() ? norm(s.head + "\n" + s.work) : all;
  const other = s.found ? norm(s.other) : "";
  const edu = s.found && s.edu.trim() ? norm(s.edu) : all;
  const texts: [string, number][] = [[work, 1], [other, 0.25]];

  const degrees = Object.entries(DEGREES).filter(([, w]) => w.some((x) => has(edu, x) || (x.length > 3 && has(all, x)))).map(([k]) => k);
  const roles = top([[work, 1]], ROLES, 2, 0.5).filter((k) => !degrees.includes(k));
  const cities = CITIES.filter((c) => {
    const names = c === "Delhi NCR" ? ["delhi", "gurgaon", "gurugram", "noida"] : c === "Bangalore" ? ["bangalore", "bengaluru"] : c === "Remote (India)" ? [] : [c.toLowerCase()];
    return names.some((n) => has(work, n)) || (!s.found && names.some((n) => has(all, n)));
  });
  return {
    years: years(s.found && s.work.trim() ? norm(s.work) : all, !(s.found && s.work.trim())),
    functions: top(texts, FN_WORDS, 3, 0.2, 2),
    backgrounds: [...degrees, ...roles].slice(0, 4),
    industries: top([[work, 1]], IND_WORDS, 4, 0.5),
    cities: (cities.length ? cities : CITIES.filter((c) => has(all, c.toLowerCase()))).slice(0, 4),
    skills: SKILLS.filter(([, ...ws]) => ws.some((w) => has(all, w))).map(([name]) => name).slice(0, 20),
    updated_at: new Date().toISOString(),
  };
}

/* ---------- scoring: the same sums as match_jobs in supabase/007 ---------- */
export const rpcArgs = (p: Profile) => ({
  p_years: p.years,
  p_functions: p.functions,
  p_backgrounds: p.backgrounds,
  p_industries: p.industries,
  p_cities: p.cities,
  p_skills: p.skills,
});

type Part = { label: string; got: number; of: number; why: string };
export function explain(j: Job, p: Profile): { score: number; parts: Part[] } {
  const parts: Part[] = [];
  const fn = FUNCS.find((f) => f[0] === j.function)?.[1] ?? "Other";
  parts.push(
    !p.functions.length
      ? { label: "Role", got: 15, of: 35, why: "Add the roles you want to score this." }
      : p.functions.includes(j.function ?? "")
        ? { label: "Role", got: 35, of: 35, why: `${fn} is one of the roles you want.` }
        : { label: "Role", got: 0, of: 35, why: `${fn} isn't one of the roles you picked.` },
  );
  const lo = j.experience_min, hi = j.experience_max, y = p.years;
  let e: Part;
  if (y == null) e = { label: "Experience", got: 10, of: 20, why: "Add your years of work to score this." };
  else if (lo == null && hi == null) e = { label: "Experience", got: 14, of: 20, why: "The post doesn't say how much experience it wants." };
  else if (y < (lo ?? 0)) e = { label: "Experience", got: Math.max(0, Math.round(20 - 7 * ((lo ?? 0) - y))), of: 20, why: `They ask for ${lo}+ years; you have ${y}.` };
  else if (hi != null && y > hi) e = { label: "Experience", got: Math.max(0, Math.round(20 - 4 * (y - hi))), of: 20, why: `They ask for up to ${hi} years; you have ${y}.` };
  else e = { label: "Experience", got: 20, of: 20, why: `Your ${y} years fit what they ask for.` };
  parts.push(e);
  const bw = j.background_wanted ?? [];
  const bl = (k: string) => BACKGROUNDS.find((b) => b[0] === k)?.[1] ?? k;
  const overlap = bw.filter((b) => p.backgrounds.includes(b));
  parts.push(
    !p.backgrounds.length
      ? { label: "Background", got: 7, of: 15, why: "Add your background to score this." }
      : overlap.length
        ? { label: "Background", got: 15, of: 15, why: `They want ${overlap.map(bl).join(", ")}, which you have.` }
        : !bw.length || bw.includes("any")
          ? { label: "Background", got: 9, of: 15, why: "They're open to most backgrounds." }
          : { label: "Background", got: 0, of: 15, why: `They want ${bw.map(bl).join(", ")}.` },
  );
  const il = INDUSTRIES.find((i) => i[0] === j.industry)?.[1];
  parts.push(
    !p.industries.length
      ? { label: "Industry", got: 5, of: 10, why: "Add industries to score this." }
      : p.industries.includes(j.industry ?? "")
        ? { label: "Industry", got: 10, of: 10, why: `${il} is an industry you know.` }
        : { label: "Industry", got: 0, of: 10, why: il ? `${il} is new to you.` : "Industry not known." },
  );
  parts.push(
    !p.cities.length
      ? { label: "City", got: 5, of: 10, why: "Add cities to score this." }
      : (j.location_city && p.cities.includes(j.location_city)) || j.work_mode === "remote"
        ? { label: "City", got: 10, of: 10, why: j.work_mode === "remote" ? "It's remote." : `It's in ${j.location_city}.` }
        : { label: "City", got: 0, of: 10, why: `It's in ${j.location_city ?? "another city"}.` },
  );
  const ks = (j.key_skills ?? []).join(" | ").toLowerCase();
  const found = p.skills.filter((s) => ks.includes(s.toLowerCase()));
  parts.push(
    !p.skills.length
      ? { label: "Skills", got: 5, of: 10, why: "Add skills to score this." }
      : { label: "Skills", got: Math.min(10, 4 * found.length), of: 10, why: found.length ? `You have ${found.slice(0, 4).join(", ")}.` : "None of your listed skills show up in this post." },
  );
  return { score: parts.reduce((n, x) => n + x.got, 0), parts };
}
export const GOOD = 70;
