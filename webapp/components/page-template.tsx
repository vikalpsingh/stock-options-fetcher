import Link from "next/link";
import { Check, ExternalLink } from "lucide-react";
import { CTA, Eyebrow, WhatsAppShare } from "./ui";

type Content = {
  eyebrow: string;
  title: string;
  intro: string;
  sections: { title: string; text: string }[];
  tips: string[];
  icon: React.ComponentType<{ className?: string }>;
};

export function PageTemplate({ content }: { content: Content }) {
  const Icon = content.icon;
  const mapUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent("Ujjain, Madhya Pradesh")}`;
  return (
    <main>
      <section className="relative overflow-hidden bg-maroon px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full border border-white/10" />
        <div className="absolute right-20 top-24 h-56 w-56 rounded-full border border-gold/20" />
        <div className="relative mx-auto max-w-7xl">
          <div className="grid items-end gap-10 lg:grid-cols-[1fr_280px]">
            <div className="max-w-3xl">
              <Eyebrow>{content.eyebrow}</Eyebrow>
              <h1 className="font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{content.title}</h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-orange-50/80">{content.intro}</p>
            </div>
            <div className="hidden aspect-square place-items-center rounded-full border border-white/15 bg-white/5 lg:grid">
              <Icon className="h-24 w-24 text-gold" />
            </div>
          </div>
        </div>
      </section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[1fr_340px]">
          <div className="space-y-6">
            {content.sections.map((section, index) => (
              <article key={section.title} className="rounded-3xl border border-stone-200 bg-white p-7 shadow-soft sm:p-9">
                <span className="text-xs font-bold tracking-widest text-saffron">0{index + 1}</span>
                <h2 className="mt-3 font-serif text-3xl font-semibold text-ink">{section.title}</h2>
                <p className="mt-4 leading-7 text-stone-600">{section.text}</p>
              </article>
            ))}
          </div>
          <aside className="space-y-6 lg:sticky lg:top-28 lg:self-start">
            <div className="rounded-3xl bg-sand p-7">
              <h2 className="font-serif text-2xl font-semibold text-ink">Keep in mind</h2>
              <ul className="mt-5 space-y-4">
                {content.tips.map((tip) => <li key={tip} className="flex gap-3 text-sm leading-6 text-stone-700"><Check className="mt-0.5 h-5 w-5 shrink-0 text-saffron" />{tip}</li>)}
              </ul>
            </div>
            <a href={mapUrl} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-3xl bg-ink p-6 font-bold text-white transition hover:bg-maroon">
              Open route in Google Maps <ExternalLink className="h-5 w-5" />
            </a>
            <WhatsAppShare text={`Planning Ujjain Kumbh 2028: ${content.title} — ${typeof window === "undefined" ? "https://indiankumbh.com/ujjain-kumbh-2028" : window.location.href}`} />
          </aside>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-6 rounded-[2rem] bg-maroon p-8 text-center text-white sm:p-12 md:flex-row md:text-left">
          <div><p className="text-sm font-bold uppercase tracking-widest text-gold">Make it yours</p><h2 className="mt-2 font-serif text-3xl font-semibold">Build your personal Ujjain plan</h2></div>
          <CTA href="/plan-my-trip">Start planning</CTA>
        </div>
      </section>
    </main>
  );
}
