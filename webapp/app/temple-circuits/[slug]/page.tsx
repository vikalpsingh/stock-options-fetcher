import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTempleCircuit, templeCircuits } from "@/src/data/templeCircuits";
import { FAQSection, HowToReachSection, ItineraryCards, OfficialDisclaimer, PackageCTA, PilgrimageHero, SacredImportanceSection, SeniorCitizenTips, StayRecommendation } from "@/src/components/pilgrimage/PilgrimageTemplates";

export function generateStaticParams() {
  return templeCircuits.map((circuit) => ({ slug: circuit.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const circuit = getTempleCircuit(slug);
  return { title: circuit ? `${circuit.title} Itinerary` : "Temple Circuit", description: circuit ? `${circuit.duration} temple circuit covering ${circuit.templesCovered.join(", ")}.` : undefined, alternates: { canonical: `/temple-circuits/${slug}` } };
}

export default async function TempleCircuitDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const circuit = getTempleCircuit(slug);
  if (!circuit) notFound();
  return <main><PilgrimageHero eyebrow="Temple circuit" title={circuit.title} subtitle={`${circuit.duration} route from ${circuit.startCity} to ${circuit.endCity}, ideal for ${circuit.idealFor.join(", ")}.`} primaryLabel="Search travel" primaryHref="/travel-tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><SacredImportanceSection text={`This circuit covers ${circuit.templesCovered.join(", ")} across ${circuit.statesCovered.join(", ")}.`} points={circuit.idealFor} /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><ItineraryCards items={circuit.templesCovered} /></div></section><HowToReachSection title={`Transport for ${circuit.title}`} text={circuit.travelModeRecommendations.join(" ")} /><SeniorCitizenTips difficulty={circuit.seniorCitizenSuitability} /><StayRecommendation sourcePage={`circuit-${slug}`} /><PackageCTA title={circuit.packageCTA} href="/packages" /><FAQSection faqs={[{ question: "Can this circuit be done with parents?", answer: `Senior citizen suitability is ${circuit.seniorCitizenSuitability}. Add rest windows and avoid same-day long drives after darshan.` }, { question: "Should I book a package?", answer: "A package may help if you need vehicles, hotels, darshan support or group coordination." }]} /></main>;
}
