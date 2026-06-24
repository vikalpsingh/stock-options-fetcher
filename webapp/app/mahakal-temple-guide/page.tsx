import type { Metadata } from "next";
import { Clock3, Landmark, Sparkles } from "lucide-react";
import guide from "@/data/mahakal-guide.json";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { FAQAccordion } from "@/components/faq-accordion";
import { MotionReveal } from "@/components/motion-reveal";
import { BhasmaAartiTimeline, DarshanPlanningCard, FamilyTipCards, MahakalHero, TemplePlanCard } from "@/components/mahakal-sections";
import { SectionTitle, TempleCard, WhatsAppShareButton } from "@/components/travel-components";
import { Card, CardContent } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Mahakaleshwar Temple Guide for Ujjain Visitors",
  description: "Plan Mahakal darshan, Bhasma Aarti, nearby Ujjain temples and a family-friendly sacred circuit without relying on uncertain timings.",
  keywords: ["Mahakal Darshan", "Bhasma Aarti guide", "Mahakaleshwar temple", "Ujjain nearby temples", "Mahakal family visit"],
  alternates: { canonical: "/mahakal-temple-guide" },
  openGraph: {
    title: "Mahakaleshwar Temple Guide for Ujjain Visitors",
    description: "Darshan guidance, nearby temples and family-friendly Ujjain plans.",
    images: ["/images/mahakal-temple-exterior.png"],
  },
};

export default function MahakalPage() {
  const faqSchema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: guide.faqs.map((item) => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })) };
  return (
    <main>
      <Breadcrumbs items={[{ label: "Mahakal Guide" }]} />
      <MahakalHero />

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionTitle eyebrow="Why Mahakal matters" title="The spiritual centre of an Ujjain journey" description="Plan the Jyotirlinga first, then build a humane temple circuit around it." />
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            <OverviewCard icon={Sparkles} title="Jyotirlinga importance" text={guide.overview.importance} />
            <OverviewCard icon={Landmark} title="Central to Ujjain" text={guide.overview.centrality} />
            <OverviewCard icon={Clock3} title="Suggested duration" text={guide.overview.duration} />
          </div>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionTitle eyebrow="Choose the right approach" title="Darshan planning options" description="Official categories, entry rules and availability can change. Treat these cards as planning structure, not confirmed temple policy." />
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{guide.darshanTypes.map((item) => <MotionReveal key={item.title}><DarshanPlanningCard item={item} /></MotionReveal>)}</div>
        </div>
      </section>

      <section className="pattern-mandala bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><BhasmaAartiTimeline steps={guide.bhasmaSteps} /></div>
      </section>

      <section id="nearby-temples" className="scroll-mt-24 bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end"><SectionTitle eyebrow="Nearby temple circuit" title="Six meaningful stops around Mahakal" description="Use Maps, check family suitability and add only the temples that fit your available energy." /><WhatsAppShareButton text="Mahakal and nearby Ujjain temple circuit: https://ujjain2028.in/mahakal-temple-guide#nearby-temples" /></div>
          <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{guide.nearbyTemples.map((temple) => <MotionReveal key={temple.id}><TempleCard temple={temple} showActions /></MotionReveal>)}</div>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Family and elderly planning" title="Protect energy for the darshan that matters most" description="Simple decisions around heat, hydration and pacing make the day more meaningful." /><div className="mt-10"><FamilyTipCards tips={guide.familyTips} /></div></div>
      </section>

      <section className="pattern-mandala bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Suggested temple plans" title="Choose a half-day or full-day circuit" description="Both plans assume flexible queues and include space for meals or rest." /><div className="mt-10 grid gap-6 lg:grid-cols-2">{guide.plans.map((plan, index) => <MotionReveal key={plan.title}><TemplePlanCard plan={plan} index={index} /></MotionReveal>)}</div></div>
      </section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[.7fr_1.3fr]"><SectionTitle eyebrow="Mahakal FAQs" title="Answers for a calmer visit" description="Reconfirm current official requirements before travel, especially for Bhasma Aarti and festival dates." /><FAQAccordion items={guide.faqs} /></div>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
    </main>
  );
}

function OverviewCard({ icon: Icon, title, text }: { icon: React.ComponentType<{ className?: string }>; title: string; text: string }) {
  return <Card className="h-full border-gold/35"><CardContent><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span><h2 className="mt-5 font-serif text-2xl">{title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>;
}
