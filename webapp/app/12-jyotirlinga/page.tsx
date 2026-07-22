import type { Metadata } from "next";
import { PillarHomePage } from "@/src/components/pilgrimage/RichPilgrimagePages";

export const metadata: Metadata = {
  title: "12 Jyotirlinga Darshan Guide | Route, History, Itinerary, Packages",
  description: "Plan 12 Jyotirlinga Darshan across India with history, stories, routes, regional circuits, senior citizen tips, stay, transport and package guidance.",
  alternates: { canonical: "/12-jyotirlinga" },
};

export default function JyotirlingaPage() {
  return <PillarHomePage pillar="jyotirlinga" />;
}
