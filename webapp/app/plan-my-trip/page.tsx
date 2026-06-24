import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { HeroSection } from "@/components/travel-components";
import { TripPlanner } from "@/components/trip-planner";

export const metadata: Metadata = {
  title: "Plan My Ujjain Trip",
  description: "Generate a free rule-based Ujjain itinerary using your starting city, trip length, visitor type, stay preference and interests.",
  keywords: ["Ujjain trip planner", "Mahakal itinerary generator", "Ujjain family itinerary", "Omkareshwar trip plan"],
  alternates: { canonical: "/plan-my-trip" },
  openGraph: { title: "Interactive Ujjain Trip Planner", description: "Build a simple Ujjain, Mahakal and Madhya Pradesh itinerary in five steps." },
};

export default function PlanPage() {
  return (
    <main>
      <Breadcrumbs items={[{ label: "Plan My Trip" }]} />
      <HeroSection compact eyebrow="Interactive five-step planner" title="Build a Ujjain trip that fits" accent="your people and pace." description="Choose your starting city, duration, visitor type, stay preference and interests. Get a static rule-based plan you can map, share and print." />
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><TripPlanner /></div>
      </section>
    </main>
  );
}
