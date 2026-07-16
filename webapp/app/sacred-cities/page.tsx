import type { Metadata } from "next";
import { PilgrimageListingPage } from "@/src/components/pilgrimage/PilgrimageListingPage";
import { sacredCities } from "@/src/data/sacredCities";

export const metadata: Metadata = { title: "Sacred City Travel Guides", description: "Sacred city guides for Ujjain, Nashik, Varanasi, Ayodhya, Haridwar, Prayagraj, Shirdi and more.", alternates: { canonical: "/sacred-cities" } };

export default function SacredCitiesPage() {
  return <PilgrimageListingPage eyebrow="Sacred cities" title="Sacred City Guides" subtitle="Practical city guides for temple darshan, stays, routes, food, senior citizen comfort and nearby itineraries." sourcePage="sacred-cities" cards={sacredCities.map((city) => ({ title: city.city, description: city.spiritualImportance, href: `/sacred-cities/${city.slug}`, badge: city.state }))} />;
}
