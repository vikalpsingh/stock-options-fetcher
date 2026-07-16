import type { Metadata } from "next";
import { PilgrimageListingPage } from "@/src/components/pilgrimage/PilgrimageListingPage";
import { templeCircuits } from "@/src/data/templeCircuits";

export const metadata: Metadata = { title: "Temple Circuit Travel Guides", description: "Practical temple circuit routes across India for families, senior citizens and groups.", alternates: { canonical: "/temple-circuits" } };

export default function TempleCircuitsPage() {
  return <PilgrimageListingPage eyebrow="Temple circuits" title="Temple Circuits" subtitle="Ready route ideas for Jyotirlinga, Kumbh, Krishna, Char Dham gateway and sacred city circuits." sourcePage="temple-circuits" cards={templeCircuits.map((c) => ({ title: c.title, description: `${c.duration} across ${c.statesCovered.join(", ")}.`, href: `/temple-circuits/${c.slug}`, badge: c.seniorCitizenSuitability }))} />;
}
