import type { Metadata } from "next";
import { PillarHomePage } from "@/src/components/pilgrimage/RichPilgrimagePages";

export const metadata: Metadata = {
  title: "Char Dham Yatra Guide | Registration, Route, History, Packages",
  description: "Plan Char Dham Yatra with practical guidance on registration, route map, history, Kedarnath, Badrinath, Gangotri, Yamunotri, senior citizen tips, stay, transport and packages.",
  alternates: { canonical: "/char-dham-yatra" },
};

export default function CharDhamPage() {
  return <PillarHomePage pillar="char-dham" />;
}
