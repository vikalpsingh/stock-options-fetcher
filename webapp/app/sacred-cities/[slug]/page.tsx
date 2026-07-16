import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getSacredCity, sacredCities } from "@/src/data/sacredCities";
import { BestTimeToVisitSection, FAQSection, HowToReachSection, ItineraryCards, OfficialDisclaimer, PackageCTA, PilgrimageHero, SacredImportanceSection, SeniorCitizenTips, StayRecommendation } from "@/src/components/pilgrimage/PilgrimageTemplates";

export function generateStaticParams() {
  return sacredCities.map((city) => ({ slug: city.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const city = getSacredCity(slug);
  return { title: city ? `${city.city} Sacred City Travel Guide` : "Sacred City Guide", description: city?.spiritualImportance, alternates: { canonical: `/sacred-cities/${slug}` } };
}

export default async function SacredCityDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const city = getSacredCity(slug);
  if (!city) notFound();
  return <main><PilgrimageHero eyebrow="Sacred city" title={`${city.city} Travel Guide`} subtitle={city.spiritualImportance} primaryLabel="Search travel" primaryHref="/travel-tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><SacredImportanceSection text={`${city.city}, ${city.state}, is important for ${city.mainTemples.join(", ")}.`} points={city.mainTemples} /><BestTimeToVisitSection bestTime={city.bestTimeToVisit} duration={city.suggestedDuration} /><HowToReachSection title={`How to reach ${city.city}`} text={`Nearest airport: ${city.nearestAirport}. Railway station: ${city.railwayStation}.`} /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><ItineraryCards items={city.topItineraries} /></div></section><SeniorCitizenTips /><StayRecommendation sourcePage={`sacred-city-${slug}`} /><PackageCTA title={city.packageCTA} href="/packages" /><FAQSection faqs={[{ question: `How many days are enough for ${city.city}?`, answer: city.suggestedDuration }, { question: "Should temple timings be verified?", answer: "Yes. Temple timings, festival queues and official access rules should be checked before travel." }]} /></main>;
}
