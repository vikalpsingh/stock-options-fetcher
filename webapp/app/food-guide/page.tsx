import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { CityFoodExplorer, FoodItineraryTimeline, FoodSafetyTips, IndoreFoodHighlights } from "@/components/food-guide-sections";
import { HeroSection, SectionTitle } from "@/components/travel-components";

export const metadata: Metadata = {
  title: "Food Guide for Ujjain, Indore and Madhya Pradesh",
  description: "Discover Poha Jalebi, Dal Bafla, Garadu, Sarafa Bazaar and family-friendly food experiences across Ujjain, Indore, Maheshwar and Bhopal.",
  keywords: ["Ujjain food guide", "Indore Sarafa Bazaar", "Madhya Pradesh food", "Poha Jalebi", "Dal Bafla", "Chappan Dukan"],
  alternates: { canonical: "/food-guide" },
  openGraph: { title: "What to Eat in Ujjain, Indore and Nearby MP", description: "A family-friendly guide to Malwa food, Indore street food and Kumbh food safety." },
};

export default function FoodPage() {
  return (
    <main>
      <Breadcrumbs items={[{ label: "Food Guide" }]} />
      <HeroSection compact eyebrow="Taste of Madhya Pradesh" title="What to Eat in Ujjain, Indore and" accent="Nearby MP Region" description="From Poha-Jalebi to Sarafa Bazaar, discover the food you should not miss during your Ujjain trip." />
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Food by city" title="Find the dishes that fit your route" description="Switch cities to see local and shared Malwa favourites, with meal weight and family guidance." /><div className="mt-10"><CityFoodExplorer /></div></div>
      </section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Indore food culture" title="Sarafa, Chappan and the art of sharing small plates" description="Plan Indore’s food experience on a night without an early darshan or long transfer the next morning." /><div className="mt-10"><IndoreFoodHighlights /></div></div>
      </section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Kumbh food safety" title="Eat for energy, not only excitement" description="Crowds, heat and long queues make hydration and meal timing part of trip planning." /><div className="mt-10"><FoodSafetyTips /></div></div>
      </section>
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-5xl"><FoodItineraryTimeline /></div>
      </section>
    </main>
  );
}
