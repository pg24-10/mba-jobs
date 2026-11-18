"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { User } from "@supabase/supabase-js";
import * as L from "@/lib/jobs";
import * as P from "@/lib/profile";
import type { F, Job } from "@/lib/jobs";
import type { Profile } from "@/lib/profile";

/* ---------- small pieces ---------- */
const PATHS: Record<L.Shape, React.ReactNode> = {
  circle: <circle cx="50" cy="50" r="50" />,
  square: <rect width="100" height="100" />,
  tri: <polygon points="50,0 100,100 0,100" />,
  half: <path d="M0 100A50 50 0 0 1 100 100Z" transform="translate(0,-25)" />,
};
const Shape = ({ kind, fill }: { kind: L.Shape; fill: string }) => (
  <svg viewBox="0 0 100 100" fill={fill} aria-hidden="true">
    {PATHS[kind]}
  </svg>
);
const Mark = () => (
  <span className="mark" aria-hidden="true">
    <svg width="16" height="16" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#D7263D" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><rect width="100" height="100" fill="#1D4ED8" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><polygon points="50,0 100,100 0,100" fill="#F5C400" /></svg>
  </span>
);
const Mag = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M15.5 15.5 21 21" />
  </svg>
);
const Bm = ({ on }: { on: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
    <path d="M6 3h12v18l-6-4.5L6 21z" />
  </svg>
);
const Dots = ({ n }: { n: number }) => (
  <span className="dots" title={`Fit ${n} of 5: how well this role suits an MBA`}>
    {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= n ? "on" : ""} />)}
    <span>Fit {n}</span>
  </span>
);
const fmt = (n: number) => n.toLocaleString("en-IN");
const DISC = "Summary written by mba-jobs. The original post has the full details.";

/* ---------- things kept on this device ---------- */
type Marks = { saved: number[]; applied: number[]; hidden: number[] };
const KEY = "mbaj:v1";
const NO_MARKS: Marks = { saved: [], applied: [], hidden: [] };
function loadMarks(): Marks {
  try {
    const o = JSON.parse(localStorage.getItem(KEY) || "{}");
    const ids = (x: unknown) => (Array.isArray(x) ? x.filter((n) => Number.isInteger(n)) : []);
    return { saved: ids(o.saved), applied: ids(o.applied), hidden: ids(o.hidden) };
  } catch {
    return NO_MARKS;
  }
}
function saveMarks(m: Marks) {
  try {
    localStorage.setItem(KEY, JSON.stringify(m));
  } catch {}
}
/** When the person last came, so we can flag roles that arrived since. Fixed for this browser tab. */
function loadSince(): string | null {
  try {
    let s = sessionStorage.getItem("mbaj:since");
    if (s === null) {
      s = localStorage.getItem("mbaj:visit") ?? "";
      sessionStorage.setItem("mbaj:since", s);
    }
    localStorage.setItem("mbaj:visit", new Date().toISOString());
    return s || null;
  } catch {
    return null;
  }
}

type Kind = keyof Marks;
const KINDS: Kind[] = ["saved", "applied", "hidden"];
/** Where in the address bar a job is: /job/123, or the older ?job=123. */
function jobInUrl(): number | null {
  return L.jobFromPath(window.location.pathname) ?? (Number(new URLSearchParams(window.location.search).get("job")) || null);
}

type Toast = { msg: string; undo?: () => void; action?: { label: string; fn: () => void } };
const PAGE = 50;

export default function Browse() {
  const [ready, setReady] = useState(false);
  const [f, setF] = useState<F>(L.DEFAULT_F);
  const [qText, setQText] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [marks, setMarks] = useState<Marks>(NO_MARKS);
  const [since, setSince] = useState<string | null>(null);
  const [newOnly, setNewOnly] = useState(false);
  const [rows, setRows] = useState<Job[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [err, setErr] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [newCount, setNewCount] = useState(0);
  const [updated, setUpdated] = useState<string | null>(null);
  const [extra, setExtra] = useState<Job | null>(null);
  const [sheet, setSheet] = useState(false);
  const [toast, setToastS] = useState<Toast | null>(null);
  const [wide, setWide] = useState(true);
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfileS] = useState<Profile | null>(null);
  const [profSheet, setProfSheet] = useState(false);
  const [matchOff, setMatchOff] = useState(false);
  const synced = useRef<Marks | null>(null);
  const pushed = useRef(false);
  const req = useRef(0);
  const toastT = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  /* ----- start: read the address bar and this device's marks ----- */
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const nf = L.readF(p);
    const j = jobInUrl();
    const mq = window.matchMedia("(min-width: 900px)");
    /* eslint-disable react-hooks/set-state-in-effect */
    setF(nf);
    setQText(nf.q);
    setJobId(j);
    setMarks(loadMarks());
    setProfileS(P.loadProfile());
    setSince(loadSince());
    setWide(mq.matches);
    setPhoneOpen(!mq.matches && !!j);
    setReady(true);
    /* eslint-enable react-hooks/set-state-in-effect */
    const onMq = () => setWide(mq.matches);
    mq.addEventListener("change", onMq);
    const onPop = () => {
      const f2 = L.readF(new URLSearchParams(window.location.search));
      const j2 = jobInUrl();
      pushed.current = false;
      setF((old) => (L.writeF(old) === L.writeF(f2) ? old : f2));
      setQText(f2.q);
      setJobId(j2);
      setPhoneOpen(!mq.matches && !!j2);
    };
    window.addEventListener("popstate", onPop);
    L.sb.rpc("last_updated").then(({ data }) => setUpdated(typeof data === "string" ? data : null));
    L.sb.auth.getSession().then(({ data }) => setUser(data.session?.user ?? null));
    const { data: sub } = L.sb.auth.onAuthStateChange((_e, s) => setUser(s?.user ?? null));
    return () => {
      mq.removeEventListener("change", onMq);
      window.removeEventListener("popstate", onPop);
      sub.subscription.unsubscribe();
    };
  }, []);

  /* ----- keep the address bar in step, so searches can be shared ----- */
  useEffect(() => {
    if (!ready) return;
    // A chosen role gets its own address, /job/123, so the link can be sent to a friend.
    const url = (jobId ? L.jobPath(jobId) : "/") + L.writeF(f);
    if (url !== window.location.pathname + window.location.search) window.history.replaceState(window.history.state, "", url);
  }, [f, jobId, ready]);

  /* ----- typing in search waits a moment before asking the database ----- */
  useEffect(() => {
    if (!ready || qText === f.q) return;
    const t = setTimeout(() => setF((o) => ({ ...o, q: qText })), 250);
    return () => clearTimeout(t);
  }, [qText, f.q, ready]);

  const setToast = useCallback((t: Toast | null) => {
    if (toastT.current) clearTimeout(toastT.current);
    setToastS(t);
    if (t) toastT.current = setTimeout(() => setToastS(null), 5000);
  }, []);

  const updMarks = useCallback((fn: (m: Marks) => Marks) => {
    setMarks((m) => {
      const n = fn(m);
      saveMarks(n);
      return n;
    });
  }, []);

  /* ----- signed in: join this device's marks and profile with the account's, then keep them in step ----- */
  const uid = user?.id ?? null;
  useEffect(() => {
    synced.current = null;
    if (!uid) return;
    let gone = false;
    (async () => {
      const [{ data: rows, error }, { data: prof }] = await Promise.all([
        L.sb.from("user_jobs").select("job_id, kind, at").order("at", { ascending: false }),
        L.sb.from("user_profiles").select("*").maybeSingle(),
      ]);
      if (gone || error) return;
      const local = loadMarks();
      const server: Marks = { saved: [], applied: [], hidden: [] };
      for (const r of (rows ?? []) as { job_id: number; kind: Kind }[]) if (KINDS.includes(r.kind)) server[r.kind].push(r.job_id);
      const merged = Object.fromEntries(KINDS.map((k) => [k, [...new Set([...local[k], ...server[k]])]])) as Marks;
      const up = KINDS.flatMap((k) => local[k].filter((id) => !server[k].includes(id)).map((id) => ({ user_id: uid, job_id: id, kind: k })));
      if (up.length) await L.sb.from("user_jobs").upsert(up, { ignoreDuplicates: true });
      if (gone) return;
      synced.current = merged;
      saveMarks(merged);
      setMarks(merged);
      // Profile: the newer one wins.
      const mine = P.loadProfile();
      const theirs = prof ? P.clean(prof as Record<string, unknown>) : null;
      if (theirs && (!mine || theirs.updated_at > mine.updated_at)) {
        P.saveProfile(theirs);
        setProfileS(theirs);
      } else if (mine) {
        await L.sb.from("user_profiles").upsert({ user_id: uid, ...mine });
      }
    })();
    return () => {
      gone = true;
    };
  }, [uid]);
  useEffect(() => {
    const was = synced.current;
    if (!uid || !was) return;
    const add = KINDS.flatMap((k) => marks[k].filter((id) => !was[k].includes(id)).map((id) => ({ user_id: uid, job_id: id, kind: k })));
    const del = KINDS.flatMap((k) => was[k].filter((id) => !marks[k].includes(id)).map((id) => [k, id] as const));
    synced.current = marks;
    if (add.length) L.sb.from("user_jobs").upsert(add, { ignoreDuplicates: true }).then(() => {});
    for (const k of KINDS) {
      const ids = del.filter(([kk]) => kk === k).map(([, id]) => id);
      if (ids.length) L.sb.from("user_jobs").delete().eq("kind", k).in("job_id", ids).then(() => {});
    }
  }, [marks, uid]);

  const setProfile = (p: Profile | null) => {
    const next = p && !P.isEmpty(p) ? { ...p, updated_at: new Date().toISOString() } : null;
    P.saveProfile(next);
    setProfileS(next);
    setMatchOff(false);
    if (uid) {
      if (next) L.sb.from("user_profiles").upsert({ user_id: uid, ...next }).then(() => {});
      else L.sb.from("user_profiles").delete().eq("user_id", uid).then(() => {});
    }
    if (next) setF((o) => ({ ...o, sort: "match" }));
    else setF((o) => (o.sort === "match" ? { ...o, sort: "fit" } : o));
    setJobId(null);
  };
  const useMatch = !!profile && !matchOff;
  const sort = !useMatch && f.sort === "match" ? "fit" : f.sort;
  const sorts = useMatch ? [L.MATCH_SORT, ...L.SORTS] : L.SORTS;
  const profKey = useMatch ? JSON.stringify(P.rpcArgs(profile!)) : "";
  /** Jobs, with a match score when there is a profile. */
  const jobsQ = useCallback(
    (opts?: { count: "exact" }) =>
      profKey
        ? L.sb.rpc("match_jobs", JSON.parse(profKey), opts).select(L.COLS + ",match")
        : L.sb.from("jobs").select(L.COLS, opts),
    [profKey],
  );
  const signIn = async () => {
    // Ask Supabase first, so a half-finished Google setup shows a message, not an error page.
    const on = await fetch(`${L.SB_URL}/auth/v1/settings`, { headers: { apikey: L.SB_KEY } })
      .then((r) => r.json())
      .then((x) => !!x?.external?.google)
      .catch(() => true);
    if (!on) return setToast({ msg: "Google sign-in isn't switched on yet. Your marks are still kept on this device." });
    const next = window.location.pathname + window.location.search;
    L.sb.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    }).then(({ error }) => {
      if (error) setToast({ msg: "Google sign-in isn't switched on yet." });
    });
  };

  /* ----- the list ----- */
  const viewIds = f.view === "jobs" ? null : marks[f.view];
  const viewKey = viewIds ? viewIds.join(",") : "";
  const buildList = useCallback(
    (from: number, size: number) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let q: any = jobsQ({ count: "exact" });
      if (f.view !== "jobs") q = q.in("id", viewKey ? viewKey.split(",").map(Number) : [-1]);
      else {
        q = L.applyFilters(q, f, { hidden: marks.hidden });
        if (newOnly && since) q = q.gt("first_seen_at", since);
      }
      return L.applySort(q, sort).range(from, from + size - 1);
    },
    // hidden is read when the filters change; hiding a role removes it on screen right away
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [f, viewKey, newOnly, since, jobsQ, sort],
  );

  /* ----- lane counts: every function, under the other filters. Asked for after the list arrives. ----- */
  const laneKey = L.writeF({ ...f, fn: "", sort: "fit", view: "jobs" }) + "|" + newOnly + "|" + since + "|" + nonce;
  const laneDone = useRef("");
  const laneReq = useRef(0);
  const loadLanes = () => {
    if (f.view !== "jobs" || laneDone.current === laneKey) return;
    laneDone.current = laneKey;
    const id = ++laneReq.current;
    // One request: the database groups by function and counts. id.count(), not count(),
    // because the public key may read only some columns, and count(*) needs the whole table.
    let q = L.applyFilters(L.sb.from("jobs").select("function, id.count()"), { ...f, fn: "" }, { hidden: marks.hidden });
    if (newOnly && since) q = q.gt("first_seen_at", since);
    Promise.resolve(q)
      .then((r: { data: unknown; error: unknown }) => {
        if (r.error) throw r.error;
        const next: Record<string, number> = Object.fromEntries(L.FUNCS.map(([k]) => [k, 0]));
        let all = 0;
        for (const row of (r.data ?? []) as { function: string | null; count: number }[]) {
          all += row.count;
          if (row.function) next[row.function] = (next[row.function] ?? 0) + row.count;
        }
        next.all = all;
        if (id === laneReq.current) setCounts(next);
      })
      .catch(() => {
        if (id === laneReq.current) laneDone.current = "";
      });
  };

  useEffect(() => {
    if (!ready) return;
    const id = ++req.current;
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    setLoading(true);
    setErr(false);
    const size = f.view === "jobs" ? PAGE : 500;
    const newQ =
      f.view === "jobs" && since
        ? L.applyFilters(L.sb.from("jobs").select("id", { count: "exact", head: true }), f, { hidden: marks.hidden }).gt("first_seen_at", since)
        : null;
    // One quiet retry if the database was busy.
    const list = () => buildList(0, size).then((r: { error: unknown }) => (r.error ? new Promise((ok) => setTimeout(ok, 700)).then(() => buildList(0, size)) : r));
    Promise.all([list(), newQ]).then(([r, n]) => {
      if (id !== req.current) return;
      if (r.error && profKey) {
        // Matching isn't set up on the database yet: show the plain list and score on this device.
        setMatchOff(true);
        return;
      }
      setLoading(false);
      if (r.error) {
        setErr(true);
        return;
      }
      setRows(r.data ?? []);
      setTotal(r.count ?? 0);
      setNewCount(n?.count ?? 0);
      listRef.current?.scrollTo({ top: 0 });
      loadLanes();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildList, ready, nonce]);

  const loadMore = () => {
    const id = req.current;
    setMore(true);
    buildList(rows.length, PAGE).then((r: { data: Job[] | null; error: unknown }) => {
      setMore(false);
      if (id !== req.current || r.error) return;
      setRows((old) => {
        const seen = new Set(old.map((x) => x.id));
        return [...old, ...(r.data ?? []).filter((x) => !seen.has(x.id))];
      });
    });
  };


  /* ----- what is on screen ----- */
  const hidden = useMemo(() => new Set(marks.hidden), [marks.hidden]);
  const shown = useMemo(() => {
    if (f.view === "jobs") return rows.filter((r) => !hidden.has(r.id));
    const keep = new Set(marks[f.view]);
    return rows.filter((r) => keep.has(r.id));
  }, [rows, hidden, f.view, marks]);
  const hiddenHere = rows.length - shown.length;
  const shownTotal = total == null ? null : f.view === "jobs" ? Math.max(0, total - hiddenHere) : shown.length;

  const selId = jobId ?? (wide ? shown[0]?.id ?? null : null);
  const job = shown.find((r) => r.id === selId) ?? rows.find((r) => r.id === selId) ?? (extra?.id === selId ? extra : null);

  // A shared link can point at a role that is not in the first page.
  useEffect(() => {
    if (!ready || jobId == null || loading) return;
    if (rows.some((r) => r.id === jobId) || extra?.id === jobId) return;
    jobsQ().eq("id", jobId).maybeSingle().then(({ data }: { data: unknown }) => {
      if (data) setExtra(data as Job);
    });
  }, [jobId, rows, extra, ready, loading, jobsQ]);

  /* ----- actions ----- */
  const change = (patch: Partial<F>) => {
    setF((o) => ({ ...o, ...patch }));
    setJobId(null);
  };
  const toggle = (k: "isb" | "sal" | "remote" | "noagency" | "norepost" | "own") => change({ [k]: !f[k] });
  const toggleIn = (k: "city" | "sen" | "mba" | "src" | "bg" | "ind" | "ct" | "stage", v: string) =>
    change({ [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] });
  const clearAll = () => {
    setF((o) => L.clearF(o));
    setQText("");
    setNewOnly(false);
    setJobId(null);
  };
  const setView = (view: F["view"]) => {
    setF((o) => ({ ...o, view }));
    setJobId(null);
    setPhoneOpen(false);
  };

  const open = (id: number) => {
    if (wide) {
      setJobId(id);
      return;
    }
    if (!pushed.current) {
      window.history.pushState(window.history.state, "", L.jobPath(id) + L.writeF(f));
      pushed.current = true;
    }
    setJobId(id);
    setPhoneOpen(true);
  };
  const closePhone = () => {
    if (pushed.current) window.history.back();
    else {
      setJobId(null);
      setPhoneOpen(false);
    }
  };

  const flip = (k: "saved" | "applied", id: number) => {
    const had = marks[k].includes(id);
    const apply = (on: boolean) => updMarks((m) => ({ ...m, [k]: on ? [id, ...m[k].filter((x) => x !== id)] : m[k].filter((x) => x !== id) }));
    apply(!had);
    const msg =
      k === "saved"
        ? had ? "Removed from Saved." : "Saved. It's in your Saved tab."
        : had ? "No longer marked as applied." : "Marked as applied. It's in your Applied tab.";
    setToast({ msg, undo: () => apply(had) });
  };
  const hide = (id: number) => {
    const idx = shown.findIndex((r) => r.id === id);
    const next = shown[idx + 1] ?? shown[idx - 1];
    updMarks((m) => ({ ...m, hidden: [id, ...m.hidden.filter((x) => x !== id)] }));
    if (wide) setJobId(next ? next.id : null);
    else if (phoneOpen) closePhone();
    setToast({
      msg: "Hidden. You won't see this role again.",
      undo: () => {
        updMarks((m) => ({ ...m, hidden: m.hidden.filter((x) => x !== id) }));
        if (wide) setJobId(id);
      },
    });
  };
  const share = async (j: Job) => {
    const url = window.location.origin + L.jobPath(j.id);
    if (!wide && navigator.share) {
      try {
        await navigator.share({ title: `${j.title} at ${j.company}`, url });
      } catch {}
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setToast({ msg: "Link copied. Anyone with it can open this role." });
    } catch {
      setToast({ msg: url });
    }
  };
  const score = (j: Job) => (profile ? j.match ?? P.explain(j, profile).score : null);
  const applied = (j: Job, site: string) => {
    if (marks.applied.includes(j.id)) return;
    setToast({
      msg: `Opened the post on ${site}. Did you apply?`,
      action: {
        label: "Mark applied",
        fn: () => {
          updMarks((m) => ({ ...m, applied: [j.id, ...m.applied.filter((x) => x !== j.id)] }));
          setToast({ msg: "Marked as applied. It's in your Applied tab." });
        },
      },
    });
  };

  /* ----- keyboard on a laptop: / search, j k move, s save, a applied, h hide ----- */
  useEffect(() => {
    if (!wide) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA") {
        if (e.key === "Escape") t.blur();
        return;
      }
      if (sheet || profSheet) {
        if (e.key === "Escape") {
          setSheet(false);
          setProfSheet(false);
        }
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (selId != null && k === "s") return flip("saved", selId);
      if (selId != null && k === "a") return flip("applied", selId);
      if (selId != null && k === "h") return hide(selId);
      const i = shown.findIndex((r) => r.id === selId);
      let n = -1;
      if (k === "j" || k === "arrowdown") n = Math.min(shown.length - 1, i + 1);
      else if (k === "k" || k === "arrowup") n = Math.max(0, i - 1);
      else return;
      e.preventDefault();
      if (n >= 0 && shown[n]) {
        setJobId(shown[n].id);
        requestAnimationFrame(() => document.querySelector(".row.sel")?.scrollIntoView({ block: "nearest" }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // No page scrolling behind the phone job page or the filter sheet.
  useEffect(() => {
    document.body.style.overflow = sheet || profSheet || (phoneOpen && !wide) ? "hidden" : "";
  }, [sheet, profSheet, phoneOpen, wide]);

  /* ---------- drawing ---------- */
  const chips = L.activeChips(f);
  // Count only filters that live inside the panel, not the pills already on screen.
  const moreCount = chips.filter(([k]) => !["q", "fn", "fit", "isb", "sal", "remote"].includes(String(k)) && !(k === "days" && f.days === 7)).length;
  const isJobs = f.view === "jobs";
  const isNew = (j: Job) => !!since && j.first_seen_at > since;

  const lanes = (
    <div className="lanes" role="group" aria-label="Job functions">
      <button
        className={"tile w" + (f.fn ? " dim" : " on")}
        style={{ flexGrow: Math.sqrt(counts.all ?? 1) / 2 }}
        onClick={() => change({ fn: "" })}
        aria-pressed={!f.fn}
      >
        <b>{counts.all != null ? fmt(counts.all) : "…"}</b>
        <small>All roles</small>
      </button>
      {L.FUNCS.map(([k, label, col, kind]) => {
        const n = counts[k];
        return (
          <button
            key={k}
            className={"tile " + col + (f.fn === k ? " on" : f.fn ? " dim" : "") + (n === 0 ? " zero" : "")}
            style={{ flexGrow: Math.sqrt(n ?? 1) }}
            onClick={() => change({ fn: f.fn === k ? "" : k })}
            aria-pressed={f.fn === k}
            title={`Show only ${L.fnLabel(k)}`}
          >
            <Shape kind={kind} fill={L.PARTNER[col]} />
            <b>{n != null ? fmt(n) : "…"}</b>
            <small>{label}</small>
          </button>
        );
      })}
    </div>
  );

  const filterRow = (
    <div className="filt">
      <button className={"pill res" + (profile ? " has" : "")} onClick={() => setProfSheet(true)}>
        {profile ? "Your profile" : "Match my resume"}
      </button>
      <button className={"pill morebtn" + (moreCount ? " on" : "")} onClick={() => setSheet(true)}>
        {wide ? "More filters" : "Filters"}
        {moreCount > 0 && <em>{moreCount}</em>}
      </button>
      <div className="seg" role="group" aria-label="Fit score">
        <span>Fit</span>
        {[1, 3, 4, 5].map((n) => (
          <button key={n} className={f.fit === n ? "on" : ""} onClick={() => change({ fit: n })} aria-pressed={f.fit === n}>
            {n === 1 ? "All" : n === 5 ? "5" : n + "+"}
          </button>
        ))}
      </div>
      {(
        [
          ["isb", "Past ISB recruiters"],
          ["sal", "Salary shown"],
          ["remote", "Remote"],
        ] as const
      ).map(([k, l]) => (
        <button key={k} className={"pill" + (f[k] ? " on" : "")} onClick={() => toggle(k)} aria-pressed={f[k]}>
          {f[k] ? "✓ " : ""}
          {l}
        </button>
      ))}
      <button className={"pill" + (f.days === 7 ? " on" : "")} onClick={() => change({ days: f.days === 7 ? 0 : 7 })} aria-pressed={f.days === 7}>
        {f.days === 7 ? "✓ " : ""}Posted this week
      </button>
      <div className="sort">
        <span>Sort</span>
        {sorts.map(([k, l]) => (
          <button key={k} className={sort === k ? "on" : ""} onClick={() => setF((o) => ({ ...o, sort: k }))}>
            {l}
          </button>
        ))}
      </div>
    </div>
  );

  const status = (
    <div className="stat" aria-live="polite">
      {!isJobs ? (
        <b>
          {shown.length} {f.view} {shown.length === 1 ? "role" : "roles"}
        </b>
      ) : shownTotal == null ? (
        <b>Loading roles…</b>
      ) : (
        <>
          <b>
            {fmt(shownTotal)} {shownTotal === 1 ? "role" : "roles"} match
          </b>
          {chips.length > 0 ? (
            <>
              <span>·</span>
              {chips.map(([k, l]) => (
                <button key={String(k)} className="chip" onClick={() => {
                  if (k === "q") setQText("");
                  setF((o) => L.removeChip(o, String(k)));
                  setJobId(null);
                }} title="Remove this filter">
                  {l} ×
                </button>
              ))}
              <button className="clr" onClick={clearAll}>Clear all</button>
            </>
          ) : (
            wide && <span>· fit 3 or better, {sort === "match" ? "best match to your resume first" : "best fit first"}</span>
          )}
          {since && (newCount > 0 || newOnly) && (
            <button className={"chip new" + (newOnly ? " on" : "")} onClick={() => { setNewOnly(!newOnly); setJobId(null); }} aria-pressed={newOnly}>
              {newOnly ? "Showing only new ×" : `${fmt(newCount)} new since your last visit`}
            </button>
          )}
        </>
      )}
      {isJobs && (
        <label className="psort">
          Sort: {sorts.find((s) => s[0] === sort)?.[1]} ▾
          <select value={sort} onChange={(e) => setF((o) => ({ ...o, sort: e.target.value }))} aria-label="Sort">
            {sorts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
      )}
      <span className="upd">{L.updatedLabel(updated)}</span>
    </div>
  );

  const list = (
    <div className={"list" + (loading && rows.length ? " busy" : "")} ref={listRef}>
      {err ? (
        <div className="err">
          Couldn&apos;t load jobs just now. <button onClick={() => setNonce((n) => n + 1)}>Try again</button>
        </div>
      ) : loading && !rows.length ? (
        Array.from({ length: 6 }, (_, i) => <div key={i} className="skel" />)
      ) : !shown.length ? (
        <div className="empty">
          {f.view === "saved" ? (
            "Nothing saved yet. Use the bookmark or Save on any role to keep it here."
          ) : f.view === "applied" ? (
            'No applications tracked yet. Use "Mark applied" after you apply on the original site.'
          ) : (
            <>No roles match these filters. <button onClick={clearAll}>Clear all filters</button></>
          )}
        </div>
      ) : (
        <>
          {shown.map((j) => {
            const [, , col, kind] = L.fnInfo(j.function);
            const saved = marks.saved.includes(j.id);
            const sel = wide && j.id === selId;
            const m = score(j);
            return (
              <div
                key={j.id}
                className={"row" + (sel ? " sel" : "")}
                onClick={() => open(j.id)}
                onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) open(j.id); }}
                role="button"
                tabIndex={0}
                aria-current={sel || undefined}
              >
                <Shape kind={kind} fill={col === "w" ? "#C9CCD1" : L.COLOR[col]} />
                <div>
                  <div className="c">
                    <span className="cn">{j.company}</span>
                    {j.past_isb_recruiter && <span className="isb">Past ISB recruiter</span>}
                    {isNew(j) && <span className="tag">New</span>}
                    {marks.applied.includes(j.id) && <span className="tag q">Applied</span>}
                    {!wide && saved && <span className="tag q">Saved</span>}
                  </div>
                  <div className="t">{j.title}</div>
                  <div className="f">
                    {m != null && <span className={"mt" + (m >= P.GOOD ? " good" : "")} title="How well this role matches your resume, out of 100">{m} match</span>}
                    {j.fit_score != null && <Dots n={j.fit_score} />}
                    <span>{L.loc(j)}</span>
                    {L.exp(j) && <span className="xl">{L.exp(j)}</span>}
                    {L.pay(j) && <b>{L.pay(j)}</b>}
                    <span>{L.posted(j)}</span>
                  </div>
                </div>
                <button
                  className={"bm" + (saved ? " on" : "")}
                  onClick={(e) => { e.stopPropagation(); flip("saved", j.id); }}
                  title={saved ? "Remove from saved" : "Save"}
                  aria-label={saved ? "Remove from saved" : "Save"}
                  aria-pressed={saved}
                >
                  <Bm on={saved} />
                </button>
              </div>
            );
          })}
          {isJobs && shownTotal != null && shown.length < shownTotal && (
            <div className="more">
              <span>Showing {fmt(shown.length)} of {fmt(shownTotal)}</span>
              <button onClick={loadMore} disabled={more}>{more ? "Loading…" : `Show ${PAGE} more`}</button>
            </div>
          )}
        </>
      )}
    </div>
  );

  const detail = job ? (
    <Detail key={job.id} j={job} marks={marks} flip={flip} hide={hide} onApply={applied} back={closePhone} share={share} profile={profile} editProfile={() => setProfSheet(true)} />
  ) : null;

  return (
    <div className="app">
      <header className="top">
        <button className="logo" onClick={() => { clearAll(); setView("jobs"); }} aria-label="mba jobs, back to all roles">
          <Mark />
          mba jobs
        </button>
        <nav className="nav" aria-label="Views">
          {(
            [
              ["jobs", "Jobs", null],
              ["saved", "Saved", marks.saved.length],
              ["applied", "Applied", marks.applied.length],
            ] as const
          ).map(([v, l, n]) => (
            <button key={v} className={f.view === v ? "on" : ""} onClick={() => setView(v)} aria-current={f.view === v || undefined}>
              {l}
              {n != null && <em>{n}</em>}
            </button>
          ))}
        </nav>
        {wide && <SearchBox q={qText} setQ={setQText} inputRef={searchRef} />}
        <div className="acct">
          <Link className="how" href="/about">How it works</Link>
          <Account user={user} signIn={signIn} openProfile={() => setProfSheet(true)} setToast={setToast} />
        </div>
      </header>
      {!wide && <SearchBox q={qText} setQ={setQText} inputRef={searchRef} />}

      {isJobs ? (
        <>
          {lanes}
          {filterRow}
        </>
      ) : (
        <div style={{ height: 8 }} />
      )}
      {status}

      <div className="main">
        {list}
        <aside className={"det" + (!wide && phoneOpen && job ? " open" : "")} aria-label="Job details">
          {detail ?? <div className="empty pick">{shown.length ? "Pick a role to see it here." : ""}</div>}
        </aside>
      </div>

      <nav className="pnav" aria-label="Views">
        {(
          [
            ["jobs", "Jobs", null],
            ["saved", "Saved", marks.saved.length],
            ["applied", "Applied", marks.applied.length],
          ] as const
        ).map(([v, l, n]) => (
          <button key={v} className={f.view === v ? "on" : ""} onClick={() => setView(v)}>
            {l}
            {n ? <em>{n}</em> : null}
          </button>
        ))}
      </nav>

      {sheet && (
        <Sheet
          f={f}
          change={change}
          toggle={toggle}
          toggleIn={toggleIn}
          total={shownTotal}
          close={() => setSheet(false)}
          clear={clearAll}
          hiddenCount={marks.hidden.length}
          unhide={() => {
            updMarks((m) => ({ ...m, hidden: [] }));
            setNonce((n) => n + 1);
            setToast({ msg: "All hidden roles are back." });
          }}
        />
      )}

      {profSheet && (
        <ProfileSheet
          profile={profile}
          signedIn={!!user}
          signIn={signIn}
          close={() => setProfSheet(false)}
          save={(p) => {
            setProfile(p);
            setProfSheet(false);
            setToast({ msg: p && !P.isEmpty(p) ? "Profile saved. Roles are now sorted by match." : "Profile deleted." });
          }}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          <span>{toast.msg}</span>
          {toast.undo && (
            <button onClick={() => { toast.undo!(); setToast(null); }}>Undo</button>
          )}
          {toast.action && <button onClick={toast.action.fn}>{toast.action.label}</button>}
        </div>
      )}
    </div>
  );
}

function SearchBox({ q, setQ, inputRef }: { q: string; setQ: (s: string) => void; inputRef: React.RefObject<HTMLInputElement | null> }) {
  return (
    <label className="search">
      <Mag />
      <span className="sr">Search roles and companies</span>
      <input
        ref={inputRef}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search roles or companies"
        autoComplete="off"
        enterKeyHint="search"
        type="search"
      />
      {q ? (
        <button className="x" onClick={(e) => { e.preventDefault(); setQ(""); }} aria-label="Clear search">×</button>
      ) : (
        <span className="kbd">/</span>
      )}
    </label>
  );
}

/* Company websites, looked up once per company. Quietly empty until supabase/007 is applied. */
const SITES = new Map<number, Promise<string | null>>();
function siteFor(id: number): Promise<string | null> {
  if (!SITES.has(id))
    SITES.set(
      id,
      (async () => {
        const { data: k } = await L.sb.from("jobs").select("company_key").eq("id", id).maybeSingle();
        const key = (k as { company_key?: string } | null)?.company_key;
        if (!key) return null;
        const { data } = await L.sb.from("company_sites").select("website").eq("company_key", key).maybeSingle();
        return (data as { website?: string } | null)?.website ?? null;
      })().catch(() => null),
    );
  return SITES.get(id)!;
}
const host = (u: string) => u.replace(/^https:\/\/(www\.)?/, "").replace(/\/.*$/, "");

function Detail({
  j, marks, flip, hide, onApply, back, share, profile, editProfile,
}: {
  j: Job;
  marks: Marks;
  flip: (k: "saved" | "applied", id: number) => void;
  hide: (id: number) => void;
  onApply: (j: Job, site: string) => void;
  back: () => void;
  share: (j: Job) => void;
  profile: Profile | null;
  editProfile: () => void;
}) {
  const [site, setSite] = useState<string | null>(null);
  useEffect(() => {
    let on = true;
    siteFor(j.id).then((w) => on && setSite(w));
    return () => {
      on = false;
    };
  }, [j.id]);
  const fit = profile ? P.explain(j, profile) : null;
  const score = j.match ?? fit?.score ?? null;
  const [, , col, kind] = L.fnInfo(j.function);
  const saved = marks.saved.includes(j.id);
  const applied = marks.applied.includes(j.id);
  const link = L.applyLink(j);
  const list = (xs: string[] | null) => (xs ?? []).filter(Boolean);
  return (
    <>
      <div className="dsc">
        <div className={"dh " + col}>
          <Shape kind={kind} fill={L.PARTNER[col]} />
          <button className="back" onClick={back} aria-label="Back to the list">←</button>
          <div>
            <span className="lbl">{L.fnLabel(j.function)}</span>
            <div className="co">
              {site ? (
                <a className="cn" href={site} target="_blank" rel="noopener noreferrer" title={`${j.company}'s website`}>
                  {j.company} <span className="ws">{host(site)} ↗</span>
                </a>
              ) : (
                <span className="cn">{j.company}</span>
              )}
              {j.past_isb_recruiter && <span className="isb">Past ISB recruiter</span>}
            </div>
            <h2>{j.title}</h2>
          </div>
        </div>
        <div className="db">
          <div className="acts">
            <button className={"act save" + (saved ? " on" : "")} onClick={() => flip("saved", j.id)} aria-pressed={saved}>
              <Bm on={saved} />
              {saved ? "Saved" : "Save"}
            </button>
            <button className={"act" + (applied ? " on" : "")} onClick={() => flip("applied", j.id)} aria-pressed={applied}>
              {applied ? "✓ Applied" : "Mark applied"}
            </button>
            <button className="act" onClick={() => hide(j.id)}>Hide</button>
            <button className="act" onClick={() => share(j)}>Share</button>
          </div>
          {j.is_stale && (
            <p className="stale">
              We first saw this role over a month ago and it may have closed. Check the original post before you spend time on it.
            </p>
          )}
          {fit && score != null && (
            <div className={"mx" + (score >= P.GOOD ? " good" : "")}>
              <div className="mx-h">
                <b>{score}</b>
                <span>match to your resume</span>
                <button onClick={editProfile}>Edit profile</button>
              </div>
              <ul>
                {fit.parts.map((x) => (
                  <li key={x.label}>
                    <span className="mx-l">{x.label}</span>
                    <span className="mx-bar" aria-hidden>
                      <i style={{ width: `${(100 * x.got) / x.of}%` }} />
                    </span>
                    <span className="mx-w">{x.why}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="kv">
            {L.facts(j).map(([a, b]) => (
              <div key={a}>
                <small>{a}</small>
                <b>{b}</b>
              </div>
            ))}
          </div>
          {j.summary && <p className="sum">{j.summary}</p>}
          {list(j.duties).length > 0 && (
            <>
              <h3>What you&apos;d do</h3>
              <ul>{list(j.duties).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </>
          )}
          {list(j.looking_for).length > 0 && (
            <>
              <h3>What they&apos;re looking for</h3>
              <ul>{list(j.looking_for).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </>
          )}
          {list(j.key_skills).length > 0 && (
            <>
              <h3>Key skills</h3>
              <div className="sk">{list(j.key_skills).map((x, i) => <span key={i}>{x}</span>)}</div>
            </>
          )}
          <p className="disc">{DISC}</p>
        </div>
      </div>
      <div className="dbar">
        <button className={"act" + (saved ? " on" : "")} onClick={() => flip("saved", j.id)} aria-label={saved ? "Remove from saved" : "Save"} aria-pressed={saved}>
          <Bm on={saved} />
        </button>
        {link ? (
          <a className="go" href={link.url} target="_blank" rel="noopener noreferrer" onClick={() => onApply(j, link.site)}>
            Read the full post and apply on {link.site} ↗
          </a>
        ) : (
          <span className="go off">The original link is missing</span>
        )}
      </div>
    </>
  );
}

function Sheet({
  f, change, toggle, toggleIn, total, close, clear, hiddenCount, unhide,
}: {
  f: F;
  change: (p: Partial<F>) => void;
  toggle: (k: "isb" | "sal" | "remote" | "noagency" | "norepost" | "own") => void;
  toggleIn: (k: "city" | "sen" | "mba" | "src" | "bg" | "ind" | "ct" | "stage", v: string) => void;
  total: number | null;
  close: () => void;
  clear: () => void;
  hiddenCount: number;
  unhide: () => void;
}) {
  const one = <T extends string | number>(cur: T, opts: [T, string][], set: (v: T) => void) => (
    <div className="opts">
      {opts.map(([v, l]) => (
        <button key={String(v)} className={"opt" + (cur === v ? " on" : "")} onClick={() => set(v)} aria-pressed={cur === v}>{l}</button>
      ))}
    </div>
  );
  const many = (k: "city" | "sen" | "mba" | "src" | "bg" | "ind" | "ct" | "stage", opts: [string, string][]) => (
    <div className="opts">
      {opts.map(([v, l]) => (
        <button key={v} className={"opt" + (f[k].includes(v) ? " on" : "")} onClick={() => toggleIn(k, v)} aria-pressed={f[k].includes(v)}>{l}</button>
      ))}
    </div>
  );
  const flag = (k: "isb" | "sal" | "remote" | "noagency" | "norepost" | "own", l: string) => (
    <button className={"opt" + (f[k] ? " on" : "")} onClick={() => toggle(k)} aria-pressed={f[k]}>{f[k] ? "✓ " : ""}{l}</button>
  );
  return (
    <>
      <div className="scrim" onClick={close} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Filters">
        <div className="sh-top">
          <h2>Filters</h2>
          <button className="sh-x" onClick={close} aria-label="Close filters">×</button>
        </div>
        <div className="sh-body">
          <div className="grp">
            <h3>Fit score</h3>
            <p>How well a role suits an MBA, from 1 to 5.</p>
            {one(f.fit, [[1, "Show all"], [3, "3 and up"], [4, "4 and up"], [5, "5 only"]], (v) => change({ fit: v }))}
          </div>
          <div className="grp">
            <h3>Posted</h3>
            {one(f.days, [[0, "Any time"], [1, "Last 24 hours"], [7, "Last 7 days"], [30, "Last 30 days"]], (v) => change({ days: v }))}
          </div>
          <div className="grp">
            <h3>City</h3>
            {many("city", L.CITIES.map((c) => [c, c]))}
            <div className="opts" style={{ marginTop: 6 }}>{flag("remote", "Remote only")}</div>
          </div>
          <div className="grp">
            <h3>Level</h3>
            {many("sen", L.SENIORITY)}
          </div>
          <div className="grp">
            <h3>Experience they ask for</h3>
            {one(f.exp, [[0, "Any"], [2, "Up to 2 yrs"], [5, "Up to 5 yrs"], [8, "Up to 8 yrs"], [12, "Up to 12 yrs"]], (v) => change({ exp: v }))}
          </div>
          <div className="grp">
            <h3>MBA</h3>
            {many("mba", L.MBA)}
          </div>
          <div className="grp">
            <h3>Background they want</h3>
            {many("bg", L.BACKGROUNDS)}
          </div>
          <div className="grp">
            <h3>Industry</h3>
            {many("ind", L.INDUSTRIES)}
          </div>
          <div className="grp">
            <h3>Company type</h3>
            {many("ct", L.COMPANY_TYPES)}
          </div>
          <div className="grp">
            <h3>Startup stage</h3>
            {many("stage", L.STAGES)}
          </div>
          <div className="grp">
            <h3>Pay</h3>
            {one(f.pay, [[0, "Any"], [10, "10+ LPA"], [20, "20+ LPA"], [30, "30+ LPA"], [50, "50+ LPA"]], (v) => change({ pay: v }))}
            <div className="opts" style={{ marginTop: 6 }}>{flag("sal", "Salary shown")}</div>
          </div>
          <div className="grp">
            <h3>Job type</h3>
            {one(f.jt, [["", "Any"], ...L.JOB_TYPES], (v) => change({ jt: v }))}
          </div>
          <div className="grp">
            <h3>Found on</h3>
            {many("src", L.SOURCES)}
            <div className="opts" style={{ marginTop: 6 }}>{flag("own", "Apply on the company's own site")}</div>
          </div>
          <div className="grp">
            <h3>Leave out</h3>
            <div className="opts">
              {flag("noagency", "Recruitment agencies")}
              {flag("norepost", "Reposted jobs")}
            </div>
          </div>
          <div className="grp">
            <h3>Recruiters</h3>
            <div className="opts">{flag("isb", "Past ISB recruiters only")}</div>
          </div>
          {hiddenCount > 0 && (
            <p className="unhide">
              You&apos;ve hidden {hiddenCount} {hiddenCount === 1 ? "role" : "roles"}. <button onClick={unhide}>Show them again</button>
            </p>
          )}
        </div>
        <div className="sh-bar">
          <button className="clr" onClick={clear}>Clear all</button>
          <button className="go" onClick={close}>
            {total == null ? "Show roles" : `Show ${fmt(total)} ${total === 1 ? "role" : "roles"}`}
          </button>
        </div>
      </div>
    </>
  );
}

function Account({
  user, signIn, openProfile, setToast,
}: {
  user: User | null;
  signIn: () => void;
  openProfile: () => void;
  setToast: (t: Toast) => void;
}) {
  const [open, setOpen] = useState(false);
  const [sure, setSure] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) {
        setOpen(false);
        setSure(false);
      }
    };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [open]);
  if (!user)
    return (
      <button className="pill gin" onClick={signIn}>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
          <path fill="#4285F4" d="M22.6 12.2c0-.8-.1-1.5-.2-2.2H12v4.2h5.9a5 5 0 0 1-2.2 3.3v2.7h3.6c2.1-1.9 3.3-4.8 3.3-8z" />
          <path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.6-2.8c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.5H2.1v2.8A11 11 0 0 0 12 23z" />
          <path fill="#FBBC05" d="M5.8 14.1a6.6 6.6 0 0 1 0-4.2V7.1H2.1a11 11 0 0 0 0 9.8l3.7-2.8z" />
          <path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.2-3.2A11 11 0 0 0 2.1 7.1l3.7 2.8C6.7 7.3 9.1 5.4 12 5.4z" />
        </svg>
        Sign in
      </button>
    );
  const name = (user.user_metadata?.full_name as string | undefined) || user.email || "You";
  const pic = user.user_metadata?.avatar_url as string | undefined;
  return (
    <div className="me" ref={ref}>
      <button className="av" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Your account">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {pic ? <img src={pic} alt="" referrerPolicy="no-referrer" /> : name[0].toUpperCase()}
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="who">
            <b>{name}</b>
            {user.email && name !== user.email && <small>{user.email}</small>}
            <small>Saved, applied and hidden roles follow you to any device.</small>
          </div>
          <button role="menuitem" onClick={() => { setOpen(false); openProfile(); }}>Your profile</button>
          <button role="menuitem" onClick={() => { setOpen(false); L.sb.auth.signOut(); }}>Sign out</button>
          {sure ? (
            <button
              role="menuitem"
              className="danger"
              onClick={async () => {
                const { error } = await L.sb.rpc("delete_my_account");
                setOpen(false);
                setSure(false);
                if (error) return setToast({ msg: "Couldn't delete your account. Try again later." });
                await L.sb.auth.signOut();
                setToast({ msg: "Account deleted. Your marks stay on this device only." });
              }}
            >
              Delete for good: your account, synced marks and profile
            </button>
          ) : (
            <button role="menuitem" className="quiet" onClick={() => setSure(true)}>Delete account…</button>
          )}
        </div>
      )}
    </div>
  );
}

function Picks({ opts, on, set }: { opts: [string, string][]; on: string[]; set: (v: string[]) => void }) {
  return (
    <div className="opts">
      {opts.map(([k, l]) => (
        <button key={k} className={"opt" + (on.includes(k) ? " on" : "")} aria-pressed={on.includes(k)} onClick={() => set(on.includes(k) ? on.filter((x) => x !== k) : [...on, k])}>
          {l}
        </button>
      ))}
    </div>
  );
}

function ProfileSheet({
  profile, signedIn, signIn, close, save,
}: {
  profile: Profile | null;
  signedIn: boolean;
  signIn: () => void;
  close: () => void;
  save: (p: Profile | null) => void;
}) {
  const [p, setP] = useState<Profile>(profile ?? P.EMPTY_PROFILE);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [paste, setPaste] = useState(false);
  const [text, setText] = useState("");
  const [skill, setSkill] = useState("");
  const read = (raw: string) => {
    const r = P.readResume(raw);
    if (P.isEmpty(r)) return setNote("Couldn't find much in that. Fill in the boxes below yourself.");
    setP(r);
    setNote("Here's what we read. Fix anything that's wrong, then save.");
  };
  const upload = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setNote(null);
    try {
      read(f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf") ? await P.pdfText(f) : await f.text());
    } catch {
      setNote("Couldn't read that file. Try a PDF, or paste the text instead.");
    }
    setBusy(false);
  };
  const up = <K extends keyof Profile>(k: K, v: Profile[K]) => setP((o) => ({ ...o, [k]: v }));
  const addSkill = () => {
    const v = skill.trim();
    if (v && !p.skills.includes(v)) up("skills", [...p.skills, v].slice(0, 30));
    setSkill("");
  };
  return (
    <>
      <div className="scrim" onClick={close} />
      <div className="sheet prof" role="dialog" aria-modal="true" aria-label="Your profile">
        <div className="sh-top">
          <h2>{profile ? "Your profile" : "Match my resume"}</h2>
          <button className="sh-x" onClick={close} aria-label="Close">×</button>
        </div>
        <div className="sh-body">
          <div className="drop">
            <label className={"pill res" + (busy ? " busy" : "")}>
              {busy ? "Reading…" : "Choose a PDF"}
              <input type="file" accept=".pdf,.txt,application/pdf,text/plain" hidden onChange={(e) => upload(e.target.files?.[0])} />
            </label>
            <button className="lnk" onClick={() => setPaste((x) => !x)}>{paste ? "Hide the text box" : "or paste the text"}</button>
            <p>Your resume is read on this device and never uploaded. Only the short profile below is kept{signedIn ? ", with your account" : ""}.</p>
          </div>
          {paste && (
            <div className="paste">
              <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste your resume here" rows={6} />
              <button className="pill" disabled={!text.trim()} onClick={() => read(text)}>Read it</button>
            </div>
          )}
          {note && <p className="note">{note}</p>}

          <h3>Years of work</h3>
          <input
            className="yrs"
            type="number"
            min={0}
            max={40}
            step={0.5}
            value={p.years ?? ""}
            onChange={(e) => up("years", e.target.value === "" ? null : Math.max(0, Math.min(40, Number(e.target.value))))}
            placeholder="e.g. 4"
          />
          <h3>Roles you want</h3>
          <Picks opts={L.FUNCS.map(([k, l]) => [k, l])} on={p.functions} set={(v) => up("functions", v)} />
          <h3>Your background</h3>
          <Picks opts={L.BACKGROUNDS.filter(([k]) => k !== "any")} on={p.backgrounds} set={(v) => up("backgrounds", v)} />
          <h3>Industries you know</h3>
          <Picks opts={L.INDUSTRIES.filter(([k]) => k !== "other")} on={p.industries} set={(v) => up("industries", v)} />
          <h3>Cities</h3>
          <Picks opts={L.CITIES.map((c) => [c, c])} on={p.cities} set={(v) => up("cities", v)} />
          <h3>Skills</h3>
          <div className="opts">
            {p.skills.map((s) => (
              <button key={s} className="opt on" onClick={() => up("skills", p.skills.filter((x) => x !== s))} aria-label={`Remove ${s}`}>
                {s} ×
              </button>
            ))}
            <input
              className="addsk"
              value={skill}
              onChange={(e) => setSkill(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSkill()}
              onBlur={addSkill}
              placeholder="Add a skill"
            />
          </div>
          {!signedIn && (
            <p className="note">
              Kept on this device. <button className="lnk" onClick={signIn}>Sign in with Google</button> to use it on your phone too.
            </p>
          )}
        </div>
        <div className="sh-bar">
          {profile && <button className="clr" onClick={() => save(null)}>Delete profile</button>}
          <button className="go" disabled={P.isEmpty(p)} onClick={() => save(p)}>Save and sort by match</button>
        </div>
      </div>
    </>
  );
}
