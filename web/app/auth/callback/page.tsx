"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { sb } from "@/lib/jobs";

// The one-time code can be swapped only once, so a second run of the effect (React dev mode
// runs effects twice) reuses the first attempt instead of racing it.
let swap: Promise<{ error: { message: string } | null }> | null = null;

// Google sends people back here after they sign in. We swap the one-time code for a session, then return.
export default function AuthCallback() {
  const [err, setErr] = useState("");
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const next = p.get("next") ?? "/";
    const safe = next.startsWith("/") && !next.startsWith("//") ? next : "/";
    const code = p.get("code");
    if (!code) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setErr(p.get("error_description") ?? "Sign-in was cancelled.");
      return;
    }
    swap ??= sb.auth.exchangeCodeForSession(code);
    swap.then(({ error }) => {
      if (error) setErr(error.message);
      else window.location.replace(safe);
    });
  }, []);
  return (
    <main className="cb">
      {err ? (
        <>
          <p>Couldn&apos;t sign you in: {err}</p>
          <Link href="/">Back to mba jobs</Link>
        </>
      ) : (
        <p>Signing you in…</p>
      )}
    </main>
  );
}
