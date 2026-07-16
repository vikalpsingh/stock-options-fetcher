import type { Metadata } from "next";
import { PilgrimageListingPage } from "@/src/components/pilgrimage/PilgrimageListingPage";
import { kumbhEvents } from "@/src/data/kumbhEvents";

export const metadata: Metadata = { title: "Kumbh Mela Travel Guides", description: "Practical Kumbh Mela guides for Nashik 2027, Ujjain 2028, Prayagraj and Haridwar.", alternates: { canonical: "/kumbh-mela" } };

export default function KumbhMelaPage() {
  return <PilgrimageListingPage eyebrow="Kumbh Mela" title="Kumbh Mela Travel Guides" subtitle="Plan Nashik-Trimbakeshwar 2027, Ujjain Simhastha 2028, Prayagraj and Haridwar with stay, route, senior citizen and crowd guidance." sourcePage="kumbh-mela" cards={kumbhEvents.map((event) => ({ title: `${event.city} ${event.eventYear || "Guide"}`, description: event.shortDescription, href: `/kumbh-mela/${event.slug}`, badge: event.status.replaceAll("_", " ") }))} />;
}
