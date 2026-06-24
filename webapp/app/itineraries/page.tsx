import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ItineraryLibrary } from "@/components/itinerary-library";
import { HeroSection, SectionTitle } from "@/components/travel-components";

export const metadata: Metadata = {
  title: "Ujjain Trip Itineraries",
  description: "Ready-made 1, 2, 3, 5 and 7-day Ujjain, Omkareshwar, Maheshwar, Mandu, Sanchi and Bhimbetka itineraries.",
  keywords: ["Ujjain itinerary", "Ujjain Omkareshwar itinerary", "Madhya Pradesh spiritual circuit", "Mahakal trip plan"],
  alternates: { canonical: "/itineraries" },
  openGraph: { title: "Ready-Made Ujjain Trip Itineraries", description: "Detailed family-friendly plans with Maps, food, stays, buffers and print options." },
};

export default function ItinerariesPage() {
  return (
    <main>
      <Breadcrumbs items={[{ label: "Trip Itineraries" }]} />
      <HeroSection compact eyebrow="No research required" title="Ujjain Trip" accent="Itineraries" description="Choose a ready-made one, two, three, five or seven-day plan with day-wise timings, stays, food, Maps and family travel guidance." />
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionTitle eyebrow="Choose a ready plan" title="From one sacred day to a complete MP circuit" description="Open any itinerary for morning, afternoon and evening plans. Print it, save it as PDF, share it or customize it." />
          <div className="mt-10"><ItineraryLibrary /></div>
        </div>
      </section>
    </main>
  );
}
