import type { Metadata } from "next";
import { PilgrimageListingPage } from "@/src/components/pilgrimage/PilgrimageListingPage";
import { charDhamStops } from "@/src/data/charDham";

export const metadata: Metadata = { title: "Char Dham Yatra Guide", description: "Char Dham Yatra registration, route map, senior citizen planning and package support.", alternates: { canonical: "/char-dham-yatra" } };

export default function CharDhamPage() {
  const cards = [
    { title: "Registration Guide", description: "Understand registration checkpoints and documents to verify before travel.", href: "/char-dham-yatra/registration", badge: "Required planning" },
    { title: "Route Map", description: "Plan the usual Yamunotri, Gangotri, Kedarnath and Badrinath sequence with buffers.", href: "/char-dham-yatra/route-map", badge: "Route" },
    { title: "Senior Citizen Guide", description: "Altitude, health, helicopter, pony/palki and rest-day advice.", href: "/char-dham-yatra/senior-citizen-guide", badge: "Elder friendly" },
    { title: "Packages", description: "Request assisted Char Dham package support from travel partners.", href: "/char-dham-yatra/packages", badge: "Package" },
    ...charDhamStops.map((stop) => ({ title: stop.templeName, description: stop.shortDescription, href: `/char-dham-yatra/${stop.slug}`, badge: stop.difficulty })),
  ];
  return <PilgrimageListingPage eyebrow="Char Dham" title="Char Dham Yatra" subtitle="Practical Char Dham planning for registration, route maps, health, altitude and senior citizen support." sourcePage="char-dham-yatra" cards={cards} />;
}
