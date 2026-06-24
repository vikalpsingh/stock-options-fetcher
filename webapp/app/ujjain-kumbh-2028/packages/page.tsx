import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, Clock3, HeartHandshake, Hotel, Landmark, ShieldCheck, Users } from "lucide-react";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { FAQAccordion } from "@/components/faq-accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PackageLeadForm } from "@/src/components/packages/PackageLeadForm";
import { getPackagesForDestination } from "@/src/data/packageCategories";

export const metadata: Metadata = {
  title: "Ujjain Kumbh 2028 Packages | Family, Senior Citizen and Group Yatra",
  description: "Compare practical Ujjain Kumbh 2028 package options for families, senior citizens, groups, Indore stays and Mahakal darshan support.",
  alternates: { canonical: "/ujjain-kumbh-2028/packages" },
  openGraph: {
    title: "Ujjain Kumbh 2028 Packages",
    description: "Request family, senior citizen, group and Indore-stay based Kumbh Yatra options from relevant travel partners.",
    images: ["/images/mahakal-ghat-temple.png"],
  },
};

const packages = getPackagesForDestination("ujjain-kumbh-2028");
const recommendations = [
  { label: "Best for families", packageSlug: "ujjain-family-2n-3d", icon: Users },
  { label: "Best for senior citizens", packageSlug: "senior-citizen-assisted-yatra", icon: HeartHandshake },
  { label: "Best for budget travellers", packageSlug: "budget-group-yatra", icon: Hotel },
  { label: "Best for Indore stay", packageSlug: "indore-stay-ujjain-day-trip", icon: Landmark },
  { label: "Best for groups", packageSlug: "corporate-society-group", icon: Users },
].map((item) => ({ ...item, package: packages.find((entry) => entry.slug === item.packageSlug)! }));

const faqs = [
  { question: "Should I stay in Ujjain or Indore?", answer: "Choose Ujjain for easier early darshan and less daily travel. Choose Indore for airport access and a wider hotel range, while keeping a generous road-transfer buffer." },
  { question: "Are package prices confirmed?", answer: "No. Any displayed price language is indicative. The travel partner confirms final price, availability, taxes, inclusions and payment terms." },
  { question: "Who operates the package?", answer: "Independent travel partners operate and fulfil packages. IndianKumbh.com is an information, discovery and enquiry platform and does not operate tours directly." },
  { question: "Are senior citizen packages available?", answer: "You can request a slower itinerary, accessible stay, shorter transfers and rest windows. Specific assistance must be confirmed in writing by the selected partner." },
  { question: "Can I book Mahakal darshan support?", answer: "You may request planning support, but official darshan and Bhasma Aarti rules must be verified through authorised temple sources. No partner should promise unauthorised access." },
  { question: "Can groups and societies request customised packages?", answer: "Yes. Societies, corporate groups and religious organisations can submit room, vehicle, meal and schedule requirements for a custom partner quote." },
];

export default function UjjainPackagesPage() {
  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((item) => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })),
  };

  return (
    <main>
      <Breadcrumbs items={[{ label: "Ujjain Kumbh 2028", href: "/ujjain-kumbh-2028" }, { label: "Packages" }]} />
      <section className="brand-gradient temple-silhouette pattern-jaali px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28">
        <div className="mx-auto max-w-7xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold"><Landmark className="h-4 w-4" />Travel partner discovery</p>
          <h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">Ujjain Kumbh 2028 Packages</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/85 sm:text-xl">Compare family, senior citizen, group and Indore-stay based Kumbh Yatra options from verified travel partners.</p>
          <Button asChild size="lg" className="mt-8"><Link href="#package-enquiry">Get Package Quote<ArrowRight className="h-4 w-4" /></Link></Button>
        </div>
      </section>

      <section className="border-b border-amber-200 bg-amber-50 px-4 py-5 sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl gap-3 text-sm leading-6 text-amber-950"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><p><strong>Important disclaimer:</strong> IndianKumbh.com does not operate packages directly. Final booking, price, inclusions and cancellation terms are confirmed by the travel partner.</p></div></section>

      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Package categories" title="Choose the kind of help you actually need" text="All prices remain indicative until a partner confirms availability and sends a written quote." />
          <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {packages.map((item) => <Card key={item.slug} className="premium-card h-full border-gold/35"><CardContent className="flex h-full flex-col"><div className="flex items-center justify-between gap-4"><span className="rounded-full bg-orange-50 px-3 py-1 text-xs font-bold text-saffron">{item.durationLabel}</span><Clock3 className="h-5 w-5 text-gold" /></div><h2 className="mt-5 font-serif text-2xl">{item.title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{item.shortDescription}</p><p className="mt-5 text-xs font-black uppercase tracking-wider text-maroon">{item.startingPriceLabel}</p><ul className="mt-4 space-y-2">{item.inclusions.slice(0, 3).map((inclusion) => <li key={inclusion} className="flex gap-2 text-xs leading-5 text-stone-600"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#168f4d]" />{inclusion}</li>)}</ul><Button asChild variant="outline" className="mt-6 w-full"><Link href={`?packageType=${item.slug}#package-enquiry`}>{item.ctaLabel}</Link></Button></CardContent></Card>)}
          </div>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Quick recommendations" title="Start with the closest match" />
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{recommendations.map(({ icon: Icon, ...item }) => <Link key={item.label} href={`?packageType=${item.package.slug}#package-enquiry`} className="rounded-3xl border border-gold/35 bg-[#fffdf8] p-5 transition hover:-translate-y-1 hover:border-saffron"><Icon className="h-6 w-6 text-saffron" /><p className="mt-5 text-xs font-black uppercase tracking-wider text-maroon">{item.label}</p><h3 className="mt-2 font-serif text-lg">{item.package.title}</h3></Link>)}</div>
        </div>
      </section>

      <section id="package-enquiry" className="scroll-mt-28 bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-5xl"><PackageLeadForm packageCategories={packages} /></div>
      </section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Book accommodation separately" title="Compare hotel options by base city" text="Hotel availability, payment and cancellation are handled on the partner website." />
          <div className="mt-8 flex flex-wrap gap-3">
            {[["Check Ujjain Hotels", "/go/booking-ujjain-hotels"], ["Check Indore Hotels", "/go/booking-indore-hotels"], ["Check Bhopal Hotels", "/go/booking-bhopal-hotels"]].map(([label, href]) => <Button key={href} asChild variant="outline"><Link href={href} rel="sponsored nofollow">{label}<ArrowRight className="h-4 w-4" /></Link></Button>)}
          </div>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[.7fr_1.3fr]"><SectionHeading eyebrow="Package FAQs" title="Know what is—and is not—being offered" /><FAQAccordion items={faqs} /></div></section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
    </main>
  );
}

function SectionHeading({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight sm:text-5xl">{title}</h2>{text && <p className="mt-4 text-lg leading-8 text-stone-600">{text}</p>}</div>;
}
