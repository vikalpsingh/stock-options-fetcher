import type { Metadata } from "next";
import { PilgrimageListingPage } from "@/src/components/pilgrimage/PilgrimageListingPage";
import { jyotirlingas } from "@/src/data/jyotirlingas";

export const metadata: Metadata = { title: "12 Jyotirlinga Darshan Guide", description: "Plan all 12 Jyotirlinga temples with routes, senior citizen difficulty, nearby places and itineraries.", alternates: { canonical: "/12-jyotirlinga" } };

export default function JyotirlingaPage() {
  const extra = [
    { title: "Complete Jyotirlinga Itinerary", description: "Build a multi-state Jyotirlinga plan with realistic travel buffers.", href: "/12-jyotirlinga/complete-itinerary", badge: "Itinerary" },
    { title: "Senior Citizen Jyotirlinga Plan", description: "Choose easier Jyotirlingas first and avoid high-altitude strain.", href: "/12-jyotirlinga/senior-citizen-plan", badge: "Senior guide" },
  ];
  return <PilgrimageListingPage eyebrow="Jyotirlinga" title="12 Jyotirlinga Darshan" subtitle="Temple-by-temple planning for all 12 Jyotirlingas, with travel routes, stay guidance and senior citizen difficulty notes." sourcePage="12-jyotirlinga" cards={[...extra, ...jyotirlingas.map((j) => ({ title: j.templeName, description: j.shortDescription, href: `/12-jyotirlinga/${j.slug}`, badge: j.seniorCitizenDifficulty }))]} />;
}
