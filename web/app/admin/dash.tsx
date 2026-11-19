"use client";

import { Component, useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import type { Session } from "@supabase/supabase-js";
import { sb } from "@/lib/jobs";

// Everything admin_dashboard() (supabase/010_admin_dashboard.sql) returns.
type Day = { day: string; n: number };
type RunDay = { day: string; source: string; machines: number; found: number; new: number; blocked: number; failed: number };
type Latest = {
  source: string; started: string; finished: string | null; machines: number; running: number;
  blocked: number; failed: number; found: number; new: number; error: string | null;
};
type Data = {
  now: string;
  jobs: { total: number; live: number; tagged: number; to_tag: number; card_only: number; too_thin: number; skipped: number; stale: number };
  tagged_by_day: Day[];
  runs_by_day: RunDay[];
  latest: Latest[];
  users: { total: number; new_7d: number; active_7d: number; active_1d: number; with_profile: number; saved: number; applied: number; hidden: number };
  signups_by_day: Day[];
  recent_users: { email: string; joined: string; last_seen: string | null; resume: boolean; marks: number }[];
};

const SOURCES: [string, string][] = [
  ["linkedin", "LinkedIn"], ["naukri", "Naukri"], ["indeed", "Indeed"], ["iimjobs", "IIMjobs"], ["ats", "Career pages"],
];
const srcName = (s: string) => SOURCES.find(([k]) => k === s)?.[1] ?? s;
const ACTIONS = "https://github.com/pg24-10/mba-jobs/actions/workflows/daily-collect.yml";

const n = (x: number | null | undefined) => (x ?? 0).toLocaleString("en-IN");
const ist = (iso: string | null, withDay = true) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit",
        ...(withDay ? { day: "numeric", month: "short" } : {}),
      })
    : "–";
const dayLabel = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const ago = (iso: string | null, now: string) => {
  if (!iso) return "never";
  const m = Math.round((new Date(now).getTime() - new Date(iso).getTime()) / 60000);
  if (m < 60) return `${m} min ago`;
  if (m < 48 * 60) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} days ago`;
};
/** The last 14 India days, oldest first, as YYYY-MM-DD. */
const lastDays = (now: string) => {
  const today = new Date(new Date(now).toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  return Array.from({ length: 14 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - 13 + i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
};

const Mark = () => (
  <span className="mark" aria-hidden="true">
    <svg width="16" height="16" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#D7263D" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><rect width="100" height="100" fill="#1D4ED8" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><polygon points="50,0 100,100 0,100" fill="#F5C400" /></svg>
  </span>
);

export default function Dash() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    sb.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const load = useCallback(async () => {
    setBusy(true);
    const { data, error } = await sb.rpc("admin_dashboard");
    setBusy(false);
    if (error) return setErr(error.message.includes("admins only") ? "admins" : error.message);
    setErr("");
    setData(data as Data);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (session) load();
  }, [session, load]);

  const signIn = () =>
    sb.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/admin` },
    });

  let body;
  if (session === undefined) body = <p className="ad-msg">Loading…</p>;
  else if (!session)
    body = (
      <div className="ad-msg">
        <p>Sign in to see the dashboard.</p>
        <button className="pill on" onClick={signIn}>Sign in with Google</button>
      </div>
    );
  else if (err === "admins")
    body = (
      <div className="ad-msg">
        <p>This page is for the site&apos;s admins only.</p>
        <p className="mut">Signed in as {session.user.email}.</p>
      </div>
    );
  else if (err) body = <p className="ad-msg">Couldn&apos;t load the dashboard: {err}</p>;
  else if (!data) body = <p className="ad-msg">Loading…</p>;
  else body = <Catch><Board d={data} /></Catch>;

  return (
    <div className="ab">
      <header className="top">
        <Link className="logo" href="/"><Mark />mba jobs</Link>
        <nav className="nav" aria-label="Pages">
          <Link href="/">Jobs</Link>
          <a href={ACTIONS} target="_blank" rel="noreferrer">GitHub runs ↗</a>
        </nav>
        {data && (
          <button className="pill ad-re" onClick={load} disabled={busy}>
            {busy ? "Refreshing…" : `Updated ${ist(data.now, false)} · Refresh`}
          </button>
        )}
      </header>
      <main className="ab-main ad">{body}</main>
    </div>
  );
}

function Board({ d }: { d: Data }) {
  const days = lastDays(d.now);
  const j = d.jobs;
  const u = d.users;
  const tagged = new Map(d.tagged_by_day.map((x) => [x.day, x.n]));
  const signups = new Map(d.signups_by_day.map((x) => [x.day, x.n]));
  const run = (day: string, src: string) => d.runs_by_day.find((r) => r.day === day && r.source === src);
  const newOn = (day: string) => d.runs_by_day.filter((r) => r.day === day).reduce((s, r) => s + (r.new ?? 0), 0);
  const maxNew = Math.max(1, ...days.map(newOn));
  const maxTag = Math.max(1, ...days.map((x) => tagged.get(x) ?? 0));

  return (
    <>
      {/* ---------- jobs ---------- */}
      <section className="ad-tiles">
        <Tile c="y" v={j.to_tag} l="Waiting to be tagged" />
        <Tile c="k" v={j.live} l="Live on the site" />
        <Tile c="b" v={j.tagged} l="Tagged so far" />
        <Tile c="w" v={j.total} l="Jobs in the database" />
      </section>
      <section className="ab-sec">
        <h2>Jobs that aren&apos;t on the site</h2>
        <div className="ad-kv">
          <KV v={j.to_tag} l="To tag" s="Have a description. Run a tagging pass in Claude Code to put them live." />
          <KV v={j.card_only} l="Card only" s="Titles that didn't look MBA-relevant, so the full post was never opened. Expected; nothing to do." />
          <KV v={j.too_thin} l="Too thin" s="Post too short to tag." />
          <KV v={j.skipped} l="Skipped by the tagger" s="Not a real job or not in India." />
          <KV v={j.stale} l="Taken down" s="Older than 30 days or gone from every board." />
        </div>
      </section>

      {/* ---------- latest run ---------- */}
      <section className="ab-sec">
        <h2>Latest daily run</h2>
        <table className="ad-t">
          <thead>
            <tr><th>Source</th><th>Started</th><th>Finished</th><th>Status</th><th className="r">Seen</th><th className="r">New</th></tr>
          </thead>
          <tbody>
            {SOURCES.map(([k, name]) => {
              const r = d.latest.find((x) => x.source === k);
              if (!r) return <tr key={k}><td>{name}</td><td colSpan={5} className="mut">No runs yet</td></tr>;
              return (
                <tr key={k}>
                  <td><b>{name}</b></td>
                  <td>{ist(r.started)}<small className="mut"> · {ago(r.started, d.now)}</small></td>
                  <td>{r.running ? "–" : ist(r.finished)}</td>
                  <td><Status r={r} /></td>
                  <td className="r">{n(r.found)}</td>
                  <td className="r"><b>{n(r.new)}</b></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {d.latest.filter((r) => r.error).map((r) => (
          <p key={r.source} className="ad-err"><b>{srcName(r.source)}:</b> {r.error}</p>
        ))}
      </section>

      {/* ---------- new jobs per day ---------- */}
      <section className="ab-sec">
        <h2>New jobs per day</h2>
        <p className="mut">India dates, by the day the run started. Red means some machines were blocked or failed.</p>
        <div className="ad-scroll">
          <table className="ad-t ad-days">
            <thead>
              <tr><th />{days.map((x) => <th key={x} className="r">{dayLabel(x)}</th>)}</tr>
            </thead>
            <tbody>
              {SOURCES.map(([k, name]) => (
                <tr key={k}>
                  <td><b>{name}</b></td>
                  {days.map((x) => {
                    const r = run(x, k);
                    const bad = r && (r.blocked || r.failed);
                    return (
                      <td
                        key={x}
                        className={"r" + (bad ? " bad" : "")}
                        title={r ? `${r.machines} machines, ${r.blocked} blocked, ${r.failed} failed, ${n(r.found)} seen` : "No run"}
                      >
                        {r ? n(r.new) : <span className="mut">–</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="sum">
                <td><b>All</b></td>
                {days.map((x) => <td key={x} className="r"><b>{newOn(x) ? n(newOn(x)) : "–"}</b></td>)}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="ad-two">
          <Bars title="New jobs" days={days} get={newOn} max={maxNew} c="b" />
          <Bars title="Jobs tagged" days={days} get={(x) => tagged.get(x) ?? 0} max={maxTag} c="y" />
        </div>
      </section>

      {/* ---------- people ---------- */}
      <section className="ad-tiles">
        <Tile c="r" v={u.total} l="People signed up" />
        <Tile c="w" v={u.new_7d} l="New this week" />
        <Tile c="w" v={u.active_7d} l="Signed in this week" />
        <Tile c="w" v={u.active_1d} l="Signed in today" />
      </section>
      <section className="ab-sec">
        <h2>People</h2>
        <div className="ad-kv">
          <KV v={u.with_profile} l="Uploaded a resume" />
          <KV v={u.saved} l="Jobs saved" />
          <KV v={u.applied} l="Marked applied" />
          <KV v={u.hidden} l="Jobs hidden" />
        </div>
        <Bars
          title="Sign-ups per day"
          days={days}
          get={(x) => signups.get(x) ?? 0}
          max={Math.max(1, ...days.map((x) => signups.get(x) ?? 0))}
          c="r"
        />
        <h3 className="ad-h3">Latest sign-ups</h3>
        {d.recent_users.length === 0 ? (
          <p className="mut">Nobody yet.</p>
        ) : (
          <div className="ad-scroll">
            <table className="ad-t">
              <thead>
                <tr><th>Email</th><th>Joined</th><th>Last signed in</th><th>Resume</th><th className="r">Marks</th></tr>
              </thead>
              <tbody>
                {d.recent_users.map((x) => (
                  <tr key={x.email + x.joined}>
                    <td>{x.email}</td>
                    <td>{ist(x.joined)}</td>
                    <td>{ago(x.last_seen, d.now)}</td>
                    <td>{x.resume ? "Yes" : <span className="mut">No</span>}</td>
                    <td className="r">{n(x.marks)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function Tile({ c, v, l }: { c: string; v: number; l: string }) {
  return (
    <div className={`ad-tile ${c}`}>
      <b>{n(v)}</b>
      <small>{l}</small>
    </div>
  );
}

function KV({ v, l, s }: { v: number; l: string; s?: string }) {
  return (
    <div>
      <b>{n(v)}</b>
      <span>{l}</span>
      {s && <small>{s}</small>}
    </div>
  );
}

function Status({ r }: { r: Latest }) {
  if (r.running) return <span className="ad-s run">Running ({r.running} of {r.machines})</span>;
  if (r.blocked) return <span className="ad-s bad">Blocked on {r.blocked} of {r.machines}</span>;
  if (r.failed) return <span className="ad-s bad">Failed on {r.failed} of {r.machines}</span>;
  return <span className="ad-s ok">OK{r.machines > 1 ? ` · ${r.machines} machines` : ""}</span>;
}

function Bars({ title, days, get, max, c }: { title: string; days: string[]; get: (d: string) => number; max: number; c: string }) {
  return (
    <figure className="ad-bars">
      <figcaption>{title}, last 14 days</figcaption>
      <div className="ad-bars-row">
        {days.map((x) => {
          const v = get(x);
          return (
            <div key={x} className="ad-bar" title={`${dayLabel(x)}: ${n(v)}`}>
              <span className="ad-bar-v">{v ? n(v) : ""}</span>
              <i className={c} style={{ height: `${(v / max) * 100}%` }} />
              <span className="ad-bar-d">{dayLabel(x).split(" ")[0]}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

/** If drawing the numbers fails, say so instead of leaving a blank page. */
class Catch extends Component<{ children: ReactNode }, { err: string }> {
  state = { err: "" };
  static getDerivedStateFromError(e: Error) {
    return { err: e.message || String(e) };
  }
  render() {
    return this.state.err ? <p className="ad-msg">The dashboard hit an error: {this.state.err}</p> : this.props.children;
  }
}
