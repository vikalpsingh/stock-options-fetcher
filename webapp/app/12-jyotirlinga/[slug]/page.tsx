import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getJyotirlinga, jyotirlingas } from "@/src/data/jyotirlingas";
import { BestTimeToVisitSection, FAQSection, HowToReachSection, ItineraryCards, OfficialDisclaimer, PackageCTA, PilgrimageHero, SacredImportanceSection, SeniorCitizenTips, StayRecommendation } from "@/src/components/pilgrimage/PilgrimageTemplates";

const specialPages = {
  "complete-itinerary": { title: "12 Jyotirlinga Complete Itinerary", text: "A practical multi-state plan should be split into regional circuits rather than rushed as one exhausting trip." },
  "senior-citizen-plan": { title: "12 Jyotirlinga Senior Citizen Plan", text: "Start with easier temples, add rest days and avoid combining long transfers with heavy darshan days." },
} as const;

export function generateStaticParams() {
  return [...jyotirlingas.map((item) => ({ slug: item.slug })), ...Object.keys(specialPages).map((slug) => ({ slug }))];
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = getJyotirlinga(slug);
  const special = specialPages[slug as keyof typeof specialPages];
  return { title: item ? `${item.templeName} Travel Guide` : special?.title || "Jyotirlinga Guide", description: item?.shortDescription || special?.text, alternates: { canonical: `/12-jyotirlinga/${slug}` } };
}

export default async function JyotirlingaDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = getJyotirlinga(slug);
  const special = specialPages[slug as keyof typeof specialPages];
  if (!item && !special) notFound();
  const title = item?.templeName || special.title;
  const text = item?.shortDescription || special.text;
  return <main><PilgrimageHero eyebrow="12 Jyotirlinga" title={title} subtitle={text} primaryLabel="Search travel" primaryHref="/travel-tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><SacredImportanceSection text={item ? `${item.templeName} is dedicated to ${item.deityName} in ${item.city}, ${item.state}.` : text} points={item ? [item.city, item.state, `Nearest airport: ${item.nearestAirport}`] : ["Regional planning", "Rest days", "Senior-friendly pacing"]} />{item && <BestTimeToVisitSection bestTime={item.bestTimeToVisit} duration={item.suggestedDuration} />}<HowToReachSection title={`How to reach ${title}`} />{item && <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><ItineraryCards items={[`${item.city} darshan`, `${item.city} + nearby places`, `${item.circuitSlug.replaceAll("-", " ")}`]} /></div></section>}<SeniorCitizenTips difficulty={item?.seniorCitizenDifficulty || "moderate"} /><StayRecommendation sourcePage={`jyotirlinga-${slug}`} /><PackageCTA title={`Need help planning ${title}?`} href="/packages" /><FAQSection faqs={[{ question: "Are darshan timings fixed?", answer: "Temple timings and special darshan rules can change. Verify from official temple sources before travel." }, { question: "How many days are needed?", answer: item?.suggestedDuration || "Plan by region with rest days between long transfers." }]} /></main>;
}
