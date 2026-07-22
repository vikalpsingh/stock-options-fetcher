import type { Metadata } from "next";
import guide from "@/data/stay-guide.json";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { FAQAccordion } from "@/components/faq-accordion";
import { MotionReveal } from "@/components/motion-reveal";
import { HeroSection, SectionTitle } from "@/components/travel-components";
import { AreaGuideCard, DetailedStayComparison, FamilyStayQuiz, StayBudgetCards, StayHelpForm, StayRecommendationCard } from "@/components/stay-guide-sections";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HotelBookingCTA } from "@/src/components/travel/HotelBookingCTA";
import { HotelSearchBox } from "@/src/components/travel/HotelSearchBox";

export const metadata: Metadata = {
  title: "Where to Stay: Ujjain vs Indore vs Bhopal",
  description: "Compare Ujjain, Indore and Bhopal for Mahakal darshan, hotels, food, airport access, family comfort and nearby Madhya Pradesh trips.",
  keywords: ["where to stay for Ujjain Kumbh", "Ujjain vs Indore hotels", "Mahakal stay guide", "Bhopal Sanchi Bhimbetka stay"],
  alternates: { canonical: "/stay-guide" },
  openGraph: { title: "Where to Stay for Ujjain Kumbh Mela 2028?", description: "A family-friendly comparison of Ujjain, Indore and Bhopal." },
};

export default function StayPage() {
  const faqSchema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: guide.faqs.map((item) => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })) };
  return (
    <main>
      <Breadcrumbs items={[{ label: "Where to Stay" }]} />
      <HeroSection compact eyebrow="Choose the right base" title="Where to Stay for Ujjain Kumbh Mela" accent="2028?" description="Compare Ujjain, Indore, and Bhopal for darshan convenience, hotels, food, airport access, and nearby destinations." />

      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Quick recommendation" title="Start with your top travel priority" description="There is no single best city—only the base that makes your family’s main goal easier." /><div className="mt-10 grid gap-6 lg:grid-cols-3">{guide.recommendations.map((item, index) => <MotionReveal key={item.city}><StayRecommendationCard item={item} featured={index === 0} /></MotionReveal>)}</div></div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Full comparison" title="Ujjain vs Indore vs Bhopal" description="Swipe the table horizontally on mobile to compare every decision factor." /><div className="mt-10"><DetailedStayComparison items={guide.comparison} /></div></div>
      </section>

      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Booking options" title="Check Hotels in Ujjain, Indore and Bhopal" description="Compare external hotel listings by base city. Final availability, price and cancellation terms are provided by Booking.com or the hotel." /><div className="mt-10 grid gap-8 xl:grid-cols-[.95fr_1.05fr]"><HotelSearchBox title="Check Hotels in Ujjain, Indore and Bhopal" sourcePage="stay-guide" /><HotelBookingCTA title="Book Stay for Ujjain Kumbh 2028" sourcePage="stay-guide" /></div><div className="mt-6 rounded-3xl border border-gold/35 bg-white p-6 sm:flex sm:items-center sm:justify-between sm:gap-6"><div><p className="text-sm font-bold text-saffron">Staying in Indore?</p><h3 className="mt-2 font-serif text-2xl">Check Indore to Ujjain buses for your darshan day.</h3><p className="mt-2 text-sm leading-6 text-stone-600">If official Kumbh traffic controls change, re-check pickup/drop points before travel.</p></div><Button asChild className="mt-5 sm:mt-0"><Link href="/go/travel?mode=bus&from=indore&to=ujjain&date=2026-07-13&campaign=ujjain-kumbh-2028&sourcePage=stay-guide" target="_blank" rel="noopener noreferrer">Check Indore to Ujjain buses<ArrowRight className="h-4 w-4" /></Link></Button></div><div className="mt-8 rounded-3xl bg-maroon p-6 text-white sm:flex sm:items-center sm:justify-between sm:gap-6 sm:p-8"><div><p className="text-sm font-bold text-gold">Need stay + transport + darshan support?</p><h3 className="mt-2 font-serif text-2xl text-white">Request a complete package quote.</h3></div><Button asChild className="mt-5 sm:mt-0"><Link href="/ujjain-kumbh-2028/packages">Explore Ujjain Packages<ArrowRight className="h-4 w-4" /></Link></Button></div></div>
      </section>

      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Neighborhood guide" title="Choose the right area within each city" description="The city is only half the decision. Area choice affects traffic, meals, airport transfers and walking." /><div className="mt-10 grid gap-6 lg:grid-cols-3">{guide.areas.map((item) => <MotionReveal key={item.city}><AreaGuideCard city={item.city} areas={item.areas} /></MotionReveal>)}</div></div>
      </section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Family decision guide" title="What matters most to your group?" description="Select the statements that fit. The recommender gives a simple starting city—not a booking decision." /><div className="mt-10"><FamilyStayQuiz items={guide.quiz} /></div></div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Stay budget" title="Choose the level of comfort you actually need" description="Prices vary dramatically by date, so these categories describe experience rather than hardcoded rates." /><div className="mt-10"><StayBudgetCards items={guide.budgets} /></div></div>
      </section>

      <section className="pattern-mandala bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><StayHelpForm /></div></section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[.7fr_1.3fr]"><SectionTitle eyebrow="Stay FAQs" title="Questions to answer before booking" description="Use refundable rates and reconfirm access arrangements as official festival plans develop." /><FAQAccordion items={guide.faqs} /></div>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
    </main>
  );
}
