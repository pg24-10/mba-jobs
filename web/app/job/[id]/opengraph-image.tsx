import { ImageResponse } from "next/og";
import { getJob } from "@/lib/server";
import { COLOR, PARTNER, fnInfo, fnLabel, loc, pay } from "@/lib/jobs";

export const alt = "A role on mba jobs";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SHAPES: Record<string, (fill: string) => React.ReactNode> = {
  circle: (f) => <circle cx="50" cy="50" r="50" fill={f} />,
  square: (f) => <rect width="100" height="100" fill={f} />,
  tri: (f) => <polygon points="50,0 100,100 0,100" fill={f} />,
  half: (f) => <path d="M0 75A50 50 0 0 1 100 75Z" fill={f} />,
};

async function jost(): Promise<ArrayBuffer | null> {
  try {
    const css = await (await fetch("https://fonts.googleapis.com/css2?family=Jost:wght@700&display=swap", { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 6.1)" } })).text();
    const url = /src: url\((.+?)\) format\('(?:truetype|opentype)'\)/.exec(css)?.[1];
    return url ? await (await fetch(url)).arrayBuffer() : null;
  } catch {
    return null;
  }
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const j = await getJob(Number(id));
  const [, , col, kind] = fnInfo(j?.function ?? null);
  const bg = col === "w" ? "#E4E5E8" : COLOR[col];
  const ink = col === "y" || col === "w" ? "#141414" : "#FFFFFF";
  const font = await jost();
  const facts = j ? [loc(j), pay(j)].filter(Boolean).join("   ") : "";
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: bg, color: ink, padding: 72, position: "relative", fontFamily: font ? "Jost" : "sans-serif" }}>
        <svg width="460" height="460" viewBox="0 0 100 100" style={{ position: "absolute", right: -150, top: -170 }}>
          {SHAPES[kind](PARTNER[col])}
        </svg>
        <div style={{ display: "flex", fontSize: 30, fontWeight: 700 }}>{j ? fnLabel(j.function) : "mba jobs"}</div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 44, fontWeight: 700, marginBottom: 12 }}>{j?.company ?? ""}</div>
          <div style={{ display: "flex", fontSize: j && j.title.length > 60 ? 58 : 72, fontWeight: 700, lineHeight: 1.05, maxWidth: 1000 }}>{j?.title ?? "Jobs in India that suit an MBA"}</div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 36, fontSize: 28 }}>
            <span>{facts}</span>
            <span style={{ fontWeight: 700 }}>mba jobs</span>
          </div>
        </div>
      </div>
    ),
    { ...size, fonts: font ? [{ name: "Jost", data: font, weight: 700, style: "normal" }] : undefined },
  );
}
