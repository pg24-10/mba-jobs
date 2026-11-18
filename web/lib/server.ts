import { cacheLife } from "next/cache";
import { createClient } from "@supabase/supabase-js";
import { COLS, SB_KEY, SB_URL, type Job } from "./jobs";

const sbServer = createClient(SB_URL, SB_KEY, { auth: { persistSession: false, autoRefreshToken: false } });

/** One job, for a shared link's title and preview image. Kept for an hour. */
export async function getJob(id: number): Promise<Job | null> {
  "use cache";
  cacheLife("hours");
  if (!Number.isSafeInteger(id) || id <= 0) return null;
  const { data } = await sbServer.from("jobs").select(COLS).eq("id", id).maybeSingle();
  return (data as unknown as Job) ?? null;
}

export const SITE = process.env.NEXT_PUBLIC_SITE_URL
  ?? (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "http://localhost:3000");
