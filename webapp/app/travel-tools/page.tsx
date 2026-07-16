import type { Metadata } from "next";
import { OfficialDisclaimer, PilgrimageHero } from "@/src/components/pilgrimage/PilgrimageTemplates";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";

export const metadata: Metadata = { title: "Pilgrimage Travel Tools", description: "Search hotels, buses, flights, trains and package quote options for Indian pilgrimage travel.", alternates: { canonical: "/travel-tools" } };

export default function TravelToolsPage() {
  return <main><PilgrimageHero eyebrow="Travel tools" title="Pilgrimage Travel Tools" subtitle="Search hotels, buses, flights, trains and package quote options through safe partner redirects. Bookings are completed on partner websites." primaryLabel="Start searching" primaryHref="#tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><section id="tools" className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><TravelSearchWidget title="Search pilgrimage travel" sourcePage="travel-tools" /></div></section></main>;
}
