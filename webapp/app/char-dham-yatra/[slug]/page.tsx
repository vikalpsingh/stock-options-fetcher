import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { charDhamStops, getCharDhamStop } from "@/src/data/charDham";
import { BestTimeToVisitSection, FAQSection, HowToReachSection, OfficialDisclaimer, PackageCTA, PilgrimageHero, SacredImportanceSection, SeniorCitizenTips } from "@/src/components/pilgrimage/PilgrimageTemplates";

const planningPages = {
  registration: { title: "Char Dham Yatra Registration", text: "Registration requirements and official portals can change by season. Verify the current Uttarakhand government process before booking travel." },
  "route-map": { title: "Char Dham Route Map", text: "The usual sequence is Yamunotri, Gangotri, Kedarnath and Badrinath, but route conditions and weather can change quickly." },
  "senior-citizen-guide": { title: "Char Dham Senior Citizen Guide", text: "Plan medical checks, altitude buffers, rest days, helicopter/pony/palki choices and slower transfers." },
  packages: { title: "Char Dham Packages", text: "Request assisted Char Dham package guidance. Final inclusions, price and cancellation terms are confirmed by travel partners." },
} as const;

export function generateStaticParams() {
  return [...charDhamStops.map((stop) => ({ slug: stop.slug })), ...Object.keys(planningPages).map((slug) => ({ slug }))];
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const stop = getCharDhamStop(slug);
  const planning = planningPages[slug as keyof typeof planningPages];
  return { title: stop ? `${stop.templeName} | Char Dham Yatra` : planning ? `${planning.title} | Char Dham Yatra` : "Char Dham", description: stop?.shortDescription || planning?.text, alternates: { canonical: `/char-dham-yatra/${slug}` } };
}

export default async function CharDhamDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const stop = getCharDhamStop(slug);
  const planning = planningPages[slug as keyof typeof planningPages];
  if (!stop && !planning) notFound();
  const title = stop?.templeName || planning.title;
  const text = stop?.shortDescription || planning.text;
  return <main><PilgrimageHero eyebrow="Char Dham Yatra" title={title} subtitle={text} primaryLabel="Search travel" primaryHref="/travel-tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><SacredImportanceSection text={text} points={stop ? [`Altitude: ${stop.altitude}`, `Base town: ${stop.nearestBaseTown}`, stop.registrationRequired ? "Registration required" : "Verify registration"] : ["Registration", "Route map", "Senior citizen planning"]} />{stop && <BestTimeToVisitSection bestTime={stop.openingSeason} duration={`Difficulty: ${stop.difficulty}`} />}<HowToReachSection title={`How to reach ${title}`} /><SeniorCitizenTips difficulty={stop?.difficulty || "moderate"} notes={stop?.seniorCitizenNotes || "Keep health, altitude, weather and rest-day buffers central to the plan."} /><PackageCTA title={`Need help with ${title}?`} href="/packages" /><FAQSection faqs={[{ question: "Should official details be verified?", answer: "Yes. Registration, road status, opening dates and helicopter/pony/palki rules must be verified from official sources." }, { question: "Is this suitable for senior citizens?", answer: "It can be, but the plan should be slower and medically cautious, especially for Kedarnath and Yamunotri." }]} /></main>;
}
