import type { Metadata } from "next";
import { faqs } from "@/data/site";
import { Eyebrow } from "@/components/ui";

export const metadata: Metadata = { title: "Frequently Asked Questions", description: "Answers to practical Ujjain Kumbh Mela 2028 travel questions." };

export default function FAQsPage() {
  const schema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map((item) => ({ "@type": "Question", name: item.q, acceptedAnswer: { "@type": "Answer", text: item.a } })) };
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl">
        <Eyebrow>Good questions, clear answers</Eyebrow>
        <h1 className="font-serif text-5xl font-semibold text-ink sm:text-6xl">Ujjain 2028 FAQs</h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-stone-600">Start here for the practical details visitors ask us most often.</p>
        <div className="mt-12 space-y-4">
          {faqs.map((item) => <details key={item.q} className="group rounded-2xl border border-stone-200 bg-white p-6 open:shadow-soft"><summary className="cursor-pointer list-none pr-8 font-serif text-xl font-semibold text-ink">{item.q}</summary><p className="mt-4 leading-7 text-stone-600">{item.a}</p></details>)}
        </div>
      </div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
    </main>
  );
}
