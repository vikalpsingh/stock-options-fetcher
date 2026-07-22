import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { kumbhEvents, getKumbhEvent } from "@/src/data/kumbhEvents";
import { getKumbhGuide, kumbhGuides } from "@/src/data/kumbhGuides";
import { KumbhGuideLanding } from "@/src/components/kumbh/KumbhGuidePage";
import { FAQSection, HowToReachSection, OfficialDisclaimer, PackageCTA, PilgrimageHero, SacredImportanceSection, SeniorCitizenTips, StayRecommendation } from "@/src/components/pilgrimage/PilgrimageTemplates";

export function generateStaticParams() {
  return [...new Set([...kumbhGuides.map((guide) => guide.slug), ...kumbhEvents.map((event) => event.slug)])].map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const guide = getKumbhGuide(slug);
  if (guide) {
    return {
      title: `${guide.title} | IndianKumbh.com`,
      description: guide.heroSubtitle,
      keywords: guide.seoKeywords,
      alternates: { canonical: `/kumbh-mela/${slug}` },
    };
  }
  const event = getKumbhEvent(slug);
  return { title: event ? `${event.city} Kumbh Travel Guide` : "Kumbh Guide", description: event?.shortDescription, alternates: { canonical: `/kumbh-mela/${slug}` } };
}

export default async function KumbhDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const guide = getKumbhGuide(slug);
  if (guide) return <KumbhGuideLanding guide={guide} />;

  const event = getKumbhEvent(slug);
  if (!event) notFound();
  const faqs = [
    { question: `Are ${event.city} Kumbh dates official?`, answer: event.keyDates },
    { question: "Where should families stay?", answer: "Choose the base city that reduces walking, late-night transfers and crowd stress. Use refundable hotel options where possible." },
    { question: "Can senior citizens travel comfortably?", answer: "Yes, with slow pacing, rest windows, early starts, medical checks and official route verification." },
  ];
  return <main><PilgrimageHero eyebrow={event.status.replaceAll("_", " ")} title={`${event.city} Kumbh ${event.eventYear || "Guide"}`} subtitle={event.shortDescription} primaryLabel="Search travel" primaryHref="/travel-tools" secondaryLabel="Package quote" secondaryHref="/packages" /><OfficialDisclaimer /><SacredImportanceSection text={`${event.city} is associated with the ${event.river} and ${event.associatedTemple}.`} points={event.bestFor} /><HowToReachSection title={`How to reach ${event.city}`} sourcePage={`kumbh-${event.slug}`} campaign={event.slug} /><StayRecommendation sourcePage={`kumbh-${event.slug}`} /><SeniorCitizenTips notes="Avoid overpacked snan-day plans, keep meeting points and medicines ready, and verify official crowd routes before travel." /><PackageCTA title={`Need help planning ${event.city} Kumbh?`} href="/packages" /><FAQSection faqs={faqs} /></main>;
}
