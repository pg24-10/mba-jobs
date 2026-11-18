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

// Words that point to each kind of work. Kept short and specific to avoid false hits.
const FN_WORDS: Record<string, string[]> = {
  sales_bd: ["business development", "sales", "key account", "account manager", "revenue target", "channel partner", "b2b sales", "enterprise sales", "pipeline"],
  program_management: ["program manager", "programme manager", "project manager", "pmo", "program management", "project management"],
  operations: ["operations", "process improvement", "lean", "six sigma", "service delivery"],
  consulting: ["consultant", "consulting", "client engagement", "engagement manager"],
  finance: ["financial planning", "fp&a", "budgeting", "forecasting", "financial analysis", "treasury", "accounting", "audit", "controllership", "taxation"],
  marketing: ["marketing", "brand", "campaign", "go-to-market", "digital marketing", "consumer insights"],
  product: ["product manager", "product management", "product roadmap", "prd", "product owner", "user research"],
  analytics: ["analytics", "data analysis", "sql", "power bi", "tableau", "dashboard", "business analyst"],
  hr: ["human resources", "talent acquisition", "recruitment", "hrbp", "learning and development", "compensation"],
  supply_chain: ["supply chain", "procurement", "sourcing", "logistics", "inventory", "demand planning", "vendor management"],
  general_management: ["general manager", "p&l", "business head", "chief of staff", "founder's office", "founders office"],
  growth: ["growth", "user acquisition", "retention", "performance marketing", "a/b test"],
  strategy: ["strategy", "strategic", "corporate development", "market entry", "business planning"],
  banking: ["investment banking", "relationship manager", "credit", "corporate banking", "wealth management", "lending"],
  investing: ["private equity", "venture capital", "investment analyst", "portfolio", "due diligence", "deal sourcing"],
  technology: ["software engineer", "developer", "full stack", "backend", "frontend", "devops", "machine learning engineer"],
};
const BG_WORDS: Record<string, string[]> = {
  mba: ["mba", "pgdm", "pgp ", "post graduate programme in management", "post graduate program in management", "master of business administration", "indian school of business", "iim "],
  consulting: ["mckinsey", "boston consulting", "bcg", "bain", "kearney", "accenture strategy", "deloitte", "pwc", "ey ", "kpmg", "consultant"],
  ca_finance: ["chartered accountant", " ca ", "cfa", "acca", "cpa"],
  sales: ["sales", "business development", "key account"],
  marketing: ["marketing", "brand manager"],
  product: ["product manager", "product owner"],
  analytics: ["data analyst", "business analyst", "analytics", "data scientist"],
  operations: ["operations manager", "operations"],
  technology: ["software engineer", "developer", "sde", "programmer"],
  engineering: ["b.tech", "btech", "b.e.", "bachelor of engineering", "bachelor of technology", "iit "],
};
const IND_WORDS: Record<string, string[]> = {
  consulting: ["consulting", "advisory"],
  technology: ["saas", "software", "it services", "cloud"],
  bfsi: ["bank", "insurance", "nbfc", "financial services"],
  fintech: ["fintech", "payments", "upi", "lending platform"],
  investing: ["private equity", "venture capital", "asset management"],
  internet: ["e-commerce", "ecommerce", "marketplace", "consumer internet", "quick commerce", "edtech", "foodtech"],
  fmcg: ["fmcg", "consumer goods", "cpg", "hindustan unilever", "procter", "nestle", "itc limited", "dabur", "marico"],
  retail: ["retail", "stores"],
  manufacturing: ["manufacturing", "plant", "automotive", "industrial"],
  healthcare: ["healthcare", "hospital", "pharma", "pharmaceutical", "medtech", "life sciences"],
  energy: ["energy", "oil and gas", "renewable", "solar", "power sector"],
  logistics: ["logistics", "shipping", "freight", "warehousing"],
  real_estate: ["real estate", "construction", "infrastructure"],
  telecom_media: ["telecom", "media", "entertainment", "broadcasting"],
  education: ["education", "university", "school"],
  public_social: ["government", "public policy", "ngo", "non-profit", "social impact", "foundation"],
};
const SKILLS = [
  "Excel", "SQL", "Python", "R", "Power BI", "Tableau", "Looker", "Google Analytics", "Salesforce", "SAP", "Oracle", "Jira",
  "Financial modelling", "Financial modeling", "Valuation", "Budgeting", "Forecasting", "FP&A", "Due diligence", "M&A",
  "Market research", "Go-to-market", "Pricing", "P&L", "Stakeholder management", "Project management", "Program management",
  "Agile", "Scrum", "Product roadmap", "A/B testing", "User research", "Wireframing", "Figma", "CRM", "Lead generation",
  "Key account management", "Negotiation", "Business development", "Partnerships", "Digital marketing", "SEO", "SEM",
  "Performance marketing", "Brand management", "Content strategy", "Social media", "Supply chain", "Procurement",
  "Vendor management", "Inventory", "Demand planning", "Six Sigma", "Lean", "Process improvement", "Operations",
  "Data analysis", "Data visualization", "Machine learning", "Statistics", "Strategy", "Business strategy", "Consulting",
  "Team leadership", "People management", "Recruitment", "Talent acquisition", "Credit analysis", "Risk management",
  "Compliance", "Investment banking", "Equity research", "Fundraising", "Communication", "Presentation",
];
const has = (t: string, w: string) => {
  const esc = w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z])${esc.trim()}([^a-z]|$)`).test(t);
};
const hits = (t: string, words: string[]) => words.reduce((n, w) => n + (has(t, w) ? 1 : 0), 0);
const MON = "(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\\.?";

/** Years of work, from "N years of experience" or from the date ranges in the resume. */
function years(t: string): number | null {
  const said = [...t.matchAll(/(\d{1,2}(?:\.\d)?)\+?\s*(?:years|yrs)\s+(?:of\s+)?(?:work\s+|professional\s+|total\s+)?experience/g)].map((m) => Number(m[1]));
  if (said.length) return Math.max(...said.filter((n) => n < 40));
  const now = new Date();
  const ranges: [number, number][] = [];
  const re = new RegExp(`(?:${MON}\\s*)?((?:19|20)\\d{2})\\s*(?:-|–|—|to)\\s*(?:(present|current|now|till date|date)|(?:${MON}\\s*)?((?:19|20)\\d{2}))`, "g");
  // Lines, or sentences when the text was pasted as one paragraph.
  for (const line of t.split(/\n|[.;|•]\s/)) {
    // Skip school and college lines, which have date ranges too.
    if (/(b\.?tech|b\.?e\.|bachelor|master|mba|pgdm|pgp|university|college|school|institute|class x|cgpa|gpa)/.test(line)) continue;
    for (const m of line.matchAll(re)) {
      const m1 = m[1] ? ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].indexOf(m[1].slice(0, 3)) : 0;
      const a = Number(m[2]) + Math.max(0, m1) / 12;
      let b: number;
      if (m[3]) b = now.getFullYear() + now.getMonth() / 12;
      else {
        const m2 = m[4] ? ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].indexOf(m[4].slice(0, 3)) : 11;
        b = Number(m[5]) + Math.max(0, m2) / 12;
      }
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

export function readResume(raw: string): Profile {
  const t = " " + raw.toLowerCase().replace(/[ \t]+/g, " ") + " ";
  const top = (words: Record<string, string[]>, max: number, min = 1) => {
    const scored = Object.entries(words)
      .map(([k, w]) => [k, hits(t, w)] as const)
      .filter(([, n]) => n >= min)
      .sort((a, b) => b[1] - a[1]);
    const best = scored[0]?.[1] ?? 0;
    return scored.filter(([, n]) => n >= best / 2).slice(0, max).map(([k]) => k);
  };
  const cities = CITIES.filter((c) => {
    const names = c === "Delhi NCR" ? ["delhi", "gurgaon", "gurugram", "noida"] : c === "Bangalore" ? ["bangalore", "bengaluru"] : c === "Remote (India)" ? [] : [c.toLowerCase()];
    return names.some((n) => has(t, n));
  });
  return {
    years: years(t),
    functions: top(FN_WORDS, 3),
    backgrounds: top(BG_WORDS, 4),
    industries: top(IND_WORDS, 3),
    cities: cities.slice(0, 4),
    skills: [...new Set(SKILLS.filter((s) => has(t, s.toLowerCase())).map((s) => (s === "Financial modeling" ? "Financial modelling" : s)))].slice(0, 20),
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
