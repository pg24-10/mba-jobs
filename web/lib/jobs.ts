import { createClient } from "@supabase/supabase-js";

// Public key: reads jobs, and with a Google sign-in, the person's own marks and profile (see supabase/).
export const SB_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!.replace(/\/rest\/v1\/?$/, "").replace(/\/$/, "");
export const SB_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const inBrowser = typeof window !== "undefined";
export const sb = createClient(SB_URL, SB_KEY, {
  auth: { persistSession: inBrowser, autoRefreshToken: inBrowser, flowType: "pkce", detectSessionInUrl: false },
});

export const COLS =
  "id,title,company,location_city,work_mode,source_links,posted_at,first_seen_at," +
  "experience_min,experience_max,salary_min_lpa,salary_max_lpa,applicants," +
  "past_isb_recruiter,function,seniority,mba_requirement,fit_score,summary," +
  "duties,looking_for,key_skills,employment_type,is_stale,background_wanted,industry";

export type Job = {
  id: number;
  title: string;
  company: string;
  location_city: string | null;
  work_mode: string | null;
  source_links: string[];
  posted_at: string | null;
  first_seen_at: string;
  experience_min: number | null;
  experience_max: number | null;
  salary_min_lpa: number | null;
  salary_max_lpa: number | null;
  applicants: number | null;
  past_isb_recruiter: boolean;
  function: string | null;
  seniority: string | null;
  mba_requirement: string | null;
  fit_score: number | null;
  summary: string | null;
  duties: string[] | null;
  looking_for: string[] | null;
  key_skills: string[] | null;
  employment_type: string | null;
  is_stale: boolean | null;
  background_wanted: string[] | null;
  industry: string | null;
  /** 0-100, only when a resume profile is set */
  match?: number;
};

/* ---------- functions: colour and shape (see DESIGN.md) ---------- */
export type Col = "y" | "b" | "r" | "k" | "w";
export type Shape = "circle" | "square" | "tri" | "half";
export const FUNCS: [key: string, label: string, col: Col, shape: Shape][] = [
  ["sales_bd", "Sales & BD", "y", "circle"],
  ["program_management", "Program mgmt", "b", "tri"],
  ["operations", "Operations", "k", "square"],
  ["consulting", "Consulting", "r", "square"],
  ["finance", "Finance", "y", "tri"],
  ["marketing", "Marketing", "r", "circle"],
  ["product", "Product", "b", "circle"],
  ["analytics", "Analytics", "b", "square"],
  ["hr", "HR", "r", "half"],
  ["supply_chain", "Supply chain", "k", "tri"],
  ["general_management", "General mgmt", "k", "half"],
  ["growth", "Growth", "y", "square"],
  ["strategy", "Strategy", "r", "tri"],
  ["banking", "Banking", "b", "half"],
  ["investing", "Investing", "y", "half"],
  ["technology", "Technology", "k", "circle"],
  ["other", "Other", "w", "circle"],
];
export const FULL_FN: Record<string, string> = {
  program_management: "Program management",
  general_management: "General management",
};
export const fnInfo = (f: string | null) =>
  FUNCS.find((x) => x[0] === f) ?? (["other", "Other", "w", "circle"] as const);
export const fnLabel = (f: string | null) => FULL_FN[f ?? ""] ?? fnInfo(f)[1];

export const COLOR: Record<Col, string> = { y: "#F5C400", b: "#1D4ED8", r: "#D7263D", k: "#141414", w: "#FFFFFF" };
export const PARTNER: Record<Col, string> = { y: "#D7263D", b: "#F5C400", r: "#F5C400", k: "#D7263D", w: "#1D4ED8" };

export const SENIORITY: [string, string][] = [
  ["entry", "Entry level"],
  ["associate", "Associate"],
  ["manager", "Manager"],
  ["senior_manager", "Senior manager"],
  ["director", "Director"],
  ["cxo", "CXO"],
];
export const MBA: [string, string][] = [
  ["required", "MBA required"],
  ["preferred", "MBA preferred"],
  ["not mentioned", "Not mentioned"],
];
export const CITIES = ["Bangalore", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai", "Kolkata", "Remote (India)"];
export const BACKGROUNDS: [string, string][] = [
  ["mba", "MBA"],
  ["consulting", "Consulting"],
  ["ca_finance", "CA / finance"],
  ["sales", "Sales"],
  ["marketing", "Marketing"],
  ["product", "Product"],
  ["analytics", "Analytics"],
  ["operations", "Operations"],
  ["technology", "Technology"],
  ["engineering", "Engineering"],
  ["domain", "Industry experience"],
  ["any", "Any background"],
];
export const INDUSTRIES: [string, string][] = [
  ["consulting", "Consulting"],
  ["technology", "Technology"],
  ["bfsi", "Banking & insurance"],
  ["fintech", "Fintech"],
  ["investing", "Investing"],
  ["internet", "Internet"],
  ["fmcg", "FMCG"],
  ["retail", "Retail"],
  ["manufacturing", "Manufacturing"],
  ["healthcare", "Healthcare"],
  ["energy", "Energy"],
  ["logistics", "Logistics"],
  ["real_estate", "Real estate"],
  ["telecom_media", "Telecom & media"],
  ["education", "Education"],
  ["public_social", "Public & social"],
  ["other", "Other"],
];
export const COMPANY_TYPES: [string, string][] = [
  ["mnc", "MNC"],
  ["indian_large", "Large Indian company"],
  ["mid_size", "Mid-size"],
  ["startup", "Startup"],
  ["nonprofit", "Nonprofit"],
  ["government", "Government"],
  ["agency", "Agency"],
];
export const STAGES: [string, string][] = [
  ["early", "Early stage"],
  ["growth", "Growth stage"],
  ["late", "Late stage"],
];
export const JOB_TYPES: [string, string][] = [
  ["full", "Full-time"],
  ["contract", "Contract"],
];
export const SOURCES: [string, string][] = [
  ["linkedin", "LinkedIn"],
  ["naukri", "Naukri"],
  ["indeed", "Indeed"],
  ["ats", "Company sites"],
  ["iimjobs", "IIMjobs"],
];
export const SORTS: [string, string][] = [
  ["fit", "Best fit"],
  ["new", "Newest"],
  ["pay", "Highest pay"],
];
export const MATCH_SORT: [string, string] = ["match", "Best match"];

/* ---------- filters live in the page address ---------- */
export type F = {
  q: string;
  fit: number; // 1 = show all
  fn: string;
  isb: boolean;
  sal: boolean;
  remote: boolean;
  days: number; // 0 = any
  city: string[];
  sen: string[];
  mba: string[];
  src: string[];
  expmin: number; // 0 = any; else jobs open to someone with at least this many years
  exp: number; // 0 = any; else jobs asking at most this many years
  bg: string[];
  ind: string[];
  ct: string[];
  stage: string[];
  jt: string; // "" | full | contract
  pay: number; // 0 = any; else pays at least this many LPA
  paymax: number; // 0 = any; else pays from at most this many LPA
  own: boolean; // apply on the company's own site
  noagency: boolean;
  norepost: boolean;
  sort: string;
  view: "jobs" | "saved" | "applied";
};

/* Pay and experience sliders. Below PAY_FLOOR a job is never shown; the top of each slider means "or more". */
export const PAY_FLOOR = 10;
export const PAY_TOP = 100;
export const EXP_TOP = 20;
/** A slider end read from the address: 0 when missing, or sitting on the slider's own ends. */
const num0 = (v: string | null, lo: number, hi: number) => {
  const n = Math.round(Number(v ?? 0) || 0);
  return n <= lo || n >= hi ? 0 : n;
};

export function readF(p: URLSearchParams): F {
  const list = (k: string) => (p.get(k) ? p.get(k)!.split(",").filter(Boolean) : []);
  const fit = Number(p.get("fit") ?? 3);
  const v = p.get("view");
  return {
    q: p.get("q") ?? "",
    fit: [1, 3, 4, 5].includes(fit) ? fit : 3,
    fn: p.get("fn") ?? "",
    isb: p.get("isb") === "1",
    sal: p.get("sal") === "1",
    remote: p.get("remote") === "1",
    days: Number(p.get("days") ?? 0) || 0,
    city: list("city"),
    sen: list("sen"),
    mba: list("mba"),
    src: list("src"),
    expmin: num0(p.get("expmin"), 0, EXP_TOP),
    exp: num0(p.get("exp"), 0, EXP_TOP),
    bg: list("bg"),
    ind: list("ind"),
    ct: list("ct"),
    stage: list("stage"),
    jt: ["full", "contract"].includes(p.get("jt") ?? "") ? p.get("jt")! : "",
    pay: num0(p.get("pay"), PAY_FLOOR, PAY_TOP),
    paymax: num0(p.get("paymax"), PAY_FLOOR, PAY_TOP),
    own: p.get("own") === "1",
    noagency: p.get("noagency") === "1",
    norepost: p.get("norepost") === "1",
    sort: ["fit", "new", "pay", "match"].includes(p.get("sort") ?? "") ? p.get("sort")! : "fit",
    view: v === "saved" || v === "applied" ? v : "jobs",
  };
}

export function writeF(f: F): string {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.fit !== 3) p.set("fit", String(f.fit));
  if (f.fn) p.set("fn", f.fn);
  if (f.isb) p.set("isb", "1");
  if (f.sal) p.set("sal", "1");
  if (f.remote) p.set("remote", "1");
  if (f.days) p.set("days", String(f.days));
  if (f.city.length) p.set("city", f.city.join(","));
  if (f.sen.length) p.set("sen", f.sen.join(","));
  if (f.mba.length) p.set("mba", f.mba.join(","));
  if (f.src.length) p.set("src", f.src.join(","));
  if (f.expmin) p.set("expmin", String(f.expmin));
  if (f.exp) p.set("exp", String(f.exp));
  for (const k of ["bg", "ind", "ct", "stage"] as const) if (f[k].length) p.set(k, f[k].join(","));
  if (f.jt) p.set("jt", f.jt);
  if (f.pay) p.set("pay", String(f.pay));
  if (f.paymax) p.set("paymax", String(f.paymax));
  if (f.own) p.set("own", "1");
  if (f.noagency) p.set("noagency", "1");
  if (f.norepost) p.set("norepost", "1");
  if (f.sort !== "fit") p.set("sort", f.sort);
  if (f.view !== "jobs") p.set("view", f.view);
  const s = p.toString();
  return s ? "?" + s : "";
}

export const DEFAULT_F = readF(new URLSearchParams());

/** Filters that are switched on, for the status line chips. */
export function activeChips(f: F): [keyof F | string, string][] {
  const a: [string, string][] = [];
  if (f.q.trim()) a.push(["q", `"${f.q.trim()}"`]);
  if (f.fn) a.push(["fn", fnInfo(f.fn)[1]]);
  if (f.fit !== 3) a.push(["fit", f.fit === 1 ? "All fit scores" : f.fit === 5 ? "Fit 5" : `Fit ${f.fit}+`]);
  if (f.isb) a.push(["isb", "Past ISB recruiters"]);
  if (f.sal) a.push(["sal", "Salary shown"]);
  if (f.remote) a.push(["remote", "Remote"]);
  if (f.days) a.push(["days", f.days === 1 ? "Posted in 24h" : `Posted in ${f.days} days`]);
  f.city.forEach((c) => a.push(["city:" + c, c]));
  f.sen.forEach((s) => a.push(["sen:" + s, SENIORITY.find((x) => x[0] === s)?.[1] ?? s]));
  f.mba.forEach((s) => a.push(["mba:" + s, MBA.find((x) => x[0] === s)?.[1] ?? s]));
  f.src.forEach((s) => a.push(["src:" + s, SOURCES.find((x) => x[0] === s)?.[1] ?? s]));
  if (f.expmin || f.exp) a.push(["exp", rangeLabel(f.expmin, f.exp, "yrs")]);
  const lists: [keyof F & ("bg" | "ind" | "ct" | "stage"), [string, string][]][] = [
    ["bg", BACKGROUNDS], ["ind", INDUSTRIES], ["ct", COMPANY_TYPES], ["stage", STAGES],
  ];
  for (const [k, opts] of lists) f[k].forEach((s) => a.push([k + ":" + s, opts.find((x) => x[0] === s)?.[1] ?? s]));
  if (f.jt) a.push(["jt", f.jt === "full" ? "Full-time" : "Contract"]);
  if (f.pay || f.paymax) a.push(["pay", "Pays " + rangeLabel(f.pay, f.paymax, "LPA")]);
  if (f.own) a.push(["own", "Apply on company site"]);
  if (f.noagency) a.push(["noagency", "No agencies"]);
  if (f.norepost) a.push(["norepost", "No reposts"]);
  return a;
}

/** "3–8 yrs", "3+ yrs", "Up to 8 yrs" for a slider's two ends (0 = open). */
export function rangeLabel(lo: number, hi: number, unit: string): string {
  if (lo && hi) return `${lo}–${hi} ${unit}`;
  if (lo) return `${lo}+ ${unit}`;
  return `Up to ${hi} ${unit}`;
}

export function removeChip(f: F, key: string): F {
  const n = { ...f };
  const [k, v] = key.split(":");
  if (v !== undefined) {
    const kk = k as "city" | "sen" | "mba" | "src" | "bg" | "ind" | "ct" | "stage";
    n[kk] = f[kk].filter((x) => x !== v);
  } else if (k === "fit") n.fit = 3;
  else if (k === "q" || k === "fn" || k === "jt") n[k] = "";
  else if (k === "days") n.days = 0;
  else if (k === "exp") { n.exp = 0; n.expmin = 0; }
  else if (k === "pay") { n.pay = 0; n.paymax = 0; }
  else (n as Record<string, unknown>)[k] = false;
  return n;
}

export const clearF = (f: F): F => ({ ...DEFAULT_F, sort: f.sort, view: f.view });

/* ---------- building the database query ---------- */
const clean = (s: string) => s.replace(/[^\p{L}\p{N}\s&+\-/.]/gu, " ").replace(/\s+/g, " ").trim();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function applyFilters(q: any, f: F, opts: { hidden: number[]; skipFn?: boolean }) {
  q = q.not("tagged_at", "is", null).eq("is_stale", false);
  // Never show roles that pay under 10 LPA. Roles that don't state pay stay.
  q = q.or(`salary_max_lpa.is.null,salary_max_lpa.gte.${PAY_FLOOR}`);
  if (f.fit > 1) q = q.gte("fit_score", f.fit);
  if (f.fn && !opts.skipFn) q = q.eq("function", f.fn);
  if (f.isb) q = q.eq("past_isb_recruiter", true);
  if (f.sal) q = q.eq("salary_shown", true);
  if (f.remote) q = q.eq("work_mode", "remote");
  if (f.days) q = q.gte("posted_at", new Date(Date.now() - f.days * 864e5).toISOString());
  if (f.city.length) q = q.in("location_city", f.city);
  if (f.sen.length) q = q.in("seniority", f.sen);
  if (f.mba.length) q = q.in("mba_requirement", f.mba);
  if (f.src.length) q = q.overlaps("sources", f.src);
  // Experience: keep roles whose asked-for range overlaps the slider's. Unstated stays in.
  if (f.exp) q = q.or(`experience_min.is.null,experience_min.lte.${f.exp}`);
  if (f.expmin) q = q.or(`experience_max.is.null,experience_max.gte.${f.expmin}`);
  if (f.noagency) q = q.eq("is_agency", false);
  if (f.norepost) q = q.eq("is_repost", false);
  if (f.bg.length) q = q.overlaps("background_wanted", f.bg);
  if (f.ind.length) q = q.in("industry", f.ind);
  if (f.ct.length) q = q.in("company_type", f.ct);
  if (f.stage.length) q = q.in("startup_stage", f.stage);
  if (f.jt === "full") q = q.ilike("employment_type", "%full%");
  if (f.jt === "contract") q = q.ilike("employment_type", "%contract%");
  // Pay: the role's range must reach the slider's range. Roles without pay drop out once it is set.
  if (f.pay) q = q.gte("salary_max_lpa", f.pay);
  if (f.paymax) q = q.lte("salary_min_lpa", f.paymax);
  if (f.own) q = q.eq("apply_on_company_site", true);
  const s = clean(f.q);
  if (s) q = q.or(`title.ilike.*${s}*,company.ilike.*${s}*`);
  if (opts.hidden.length) q = q.not("id", "in", `(${opts.hidden.join(",")})`);
  return q;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function applySort(q: any, sort: string) {
  if (sort === "match")
    return q
      .order("match", { ascending: false })
      .order("fit_score", { ascending: false })
      .order("id", { ascending: false });
  if (sort === "new") return q.order("posted_at", { ascending: false, nullsFirst: false }).order("id", { ascending: false });
  if (sort === "pay")
    return q
      .order("salary_max_lpa", { ascending: false, nullsFirst: false })
      .order("fit_score", { ascending: false })
      .order("id", { ascending: false });
  return q
    .order("fit_score", { ascending: false })
    .order("posted_at", { ascending: false, nullsFirst: false })
    .order("id", { ascending: false });
}

/* ---------- how facts are shown ---------- */
const num = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
export function pay(j: Job): string {
  const a = j.salary_min_lpa, b = j.salary_max_lpa;
  if (a && b && a !== b) return `₹${num(a)}–${num(b)} LPA`;
  if (a || b) return `₹${num((a || b)!)} LPA`;
  return "";
}
export function exp(j: Job): string {
  const a = j.experience_min, b = j.experience_max;
  if (a != null && b != null && a !== b) return `${num(a)}–${num(b)} yrs`;
  if (a != null) return `${num(a)}+ yrs`;
  if (b != null) return `Up to ${num(b)} yrs`;
  return "";
}
export function loc(j: Job): string {
  const mode = j.work_mode ? j.work_mode[0].toUpperCase() + j.work_mode.slice(1) : "";
  if (!j.location_city) return mode || "India";
  return mode && mode !== "Onsite" ? `${j.location_city} · ${mode}` : j.location_city;
}
export function ago(iso: string | null): string {
  if (!iso) return "";
  const h = Math.max(0, (Date.now() - new Date(iso).getTime()) / 36e5);
  if (h < 1) return "Just now";
  if (h < 24) return `${Math.floor(h)}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}
export const posted = (j: Job) => ago(j.posted_at ?? j.first_seen_at);

const BOARDS: [RegExp, string, number][] = [
  [/linkedin\./, "LinkedIn", 2],
  [/naukri\./, "Naukri", 3],
  [/indeed\./, "Indeed", 4],
  [/iimjobs\./, "IIMjobs", 5],
];
/** The link the apply button opens: the company's own site first, then the job boards. */
export function applyLink(j: Job): { url: string; site: string } | null {
  const opts = (j.source_links ?? [])
    .filter((u) => /^https?:\/\//.test(u))
    .map((u) => {
      const b = BOARDS.find(([re]) => re.test(new URL(u).hostname));
      return { url: u, site: b ? b[1] : "the company site", rank: b ? b[2] : 1 };
    })
    .sort((a, b) => a.rank - b.rank);
  return opts[0] ?? null;
}

export function facts(j: Job): [string, string][] {
  return [
    ["Location", loc(j)],
    ["Experience", exp(j) || "Not stated"],
    ["Salary", pay(j) || "Not shown"],
    ["Function", fnLabel(j.function)],
    ["Level", SENIORITY.find((s) => s[0] === j.seniority)?.[1] ?? "Not stated"],
    ["MBA", MBA.find((s) => s[0] === j.mba_requirement)?.[1].replace("MBA ", "").replace(/^./, (c) => c.toUpperCase()) ?? "Not mentioned"],
    ["Posted", posted(j) + (applyLink(j) ? " on " + applyLink(j)!.site.replace("the company site", "company site") : "")],
    ["Applicants", j.applicants ? (j.applicants >= 200 ? "200+" : String(j.applicants)) : "Not shown"],
  ];
}

export function updatedLabel(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const s = d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
  return `Updated ${s} IST`;
}

/** The address of a job's own page, which can be shared. */
export const jobPath = (id: number) => `/job/${id}`;
export function jobFromPath(path: string): number | null {
  const m = /^\/job\/(\d+)\/?$/.exec(path);
  return m ? Number(m[1]) : null;
}
