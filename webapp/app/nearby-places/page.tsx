import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { CircuitCards, NearbyDestinationExplorer, NearbyTravelTips } from "@/components/nearby-destinations";
import { HeroSection, SectionTitle } from "@/components/travel-components";

export const metadata: Metadata = {
  title: "Best Places to Visit Near Ujjain",
  description: "Discover Jyotirlinga trips, Narmada ghats, heritage forts, food trails, waterfalls and UNESCO sites near Ujjain.",
  keywords: ["places near Ujjain", "Omkareshwar from Ujjain", "Maheshwar Mandu trip", "Sanchi Bhimbetka itinerary", "Tincha Falls"],
  alternates: { canonical: "/nearby-places" },
  openGraph: { title: "Best Places to Visit Near Ujjain", description: "Filter spiritual, heritage, food, nature and family trips around Ujjain." },
};

export default function NearbyPage() {
  return (
    <main>
      <Breadcrumbs items={[{ label: "Nearby Destinations" }]} />
      <HeroSection compact eyebrow="Explore around Ujjain" title="Best Places to Visit" accent="Near Ujjain" description="Plan Jyotirlinga trips, Narmada ghats, heritage forts, food trails, waterfalls, and UNESCO sites around Ujjain." />
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionTitle eyebrow="Choose by available time" title="Filter eight nearby destinations" description="Travel times are planning placeholders. Reconfirm current roads, weather, access and festival diversions before leaving." />
          <div className="mt-10"><NearbyDestinationExplorer /></div>
        </div>
      </section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Ready-made circuits" title="Combine places without unnecessary backtracking" description="These simple timelines group destinations around practical base cities." /><div className="mt-10"><CircuitCards /></div></div>
      </section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Travel planning tips" title="Keep the journey spacious" description="A good side trip should add meaning, not fatigue." /><div className="mt-10"><NearbyTravelTips /></div></div>
      </section>
    </main>
  );
}
