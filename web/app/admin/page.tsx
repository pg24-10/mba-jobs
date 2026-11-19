import type { Metadata } from "next";
import Dash from "./dash";

export const metadata: Metadata = {
  title: "Dashboard · mba jobs",
  robots: { index: false, follow: false },
};

export default function Admin() {
  return <Dash />;
}
