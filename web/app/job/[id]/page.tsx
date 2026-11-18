import { Suspense } from "react";
import type { Metadata } from "next";
import { connection } from "next/server";
import Browse from "../../browse";
import { getJob } from "@/lib/server";
import { loc, pay } from "@/lib/jobs";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const j = await getJob(Number(id));
  if (!j) return { title: "Role not found · mba jobs" };
  const title = `${j.title} at ${j.company}`;
  const description = [loc(j), pay(j), j.summary].filter(Boolean).join(" · ").slice(0, 200);
  return {
    title: `${title} · mba jobs`,
    description,
    openGraph: { title, description, type: "website", siteName: "mba jobs" },
    twitter: { card: "summary_large_image", title, description },
  };
}

// A shared job's title is read when the link is opened, so this page is built per request.
const Connection = async () => {
  await connection();
  return null;
};

export default function JobPage() {
  return (
    <>
      <Browse />
      <Suspense>
        <Connection />
      </Suspense>
    </>
  );
}
