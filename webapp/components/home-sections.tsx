import Link from "next/link";
import {
  Accessibility,
  ArrowRight,
  Check,
  Languages,
  Map,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";

const trustIcons = {
  family: Users,
  accessibility: Accessibility,
  languages: Languages,
  map: Map,
  verified: ShieldCheck,
};

export function HomeTrustSection({ items }: { items: { label: string; description: string; icon: string }[] }) {
  return (
    <section className="border-b border-stone-200 bg-white">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-5 px-4 py-7 sm:px-6 md:grid-cols-3 lg:grid-cols-5 lg:px-8">
        {items.map((item) => {
          const Icon = trustIcons[item.icon as keyof typeof trustIcons] ?? Sparkles;
          return <div key={item.label} className="flex gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-orange-50 text-saffron"><Icon className="h-5 w-5" /></span><div><p className="text-sm font-extrabold text-ink">{item.label}</p><p className="mt-1 text-xs leading-4 text-stone-500">{item.description}</p></div></div>;
        })}
      </div>
    </section>
  );
}

export function HomeStayCard({ stay, featured = false }: { stay: { city: string; bestFor: string; description: string; points: string[] }; featured?: boolean }) {
  return (
    <Card className={`relative h-full overflow-hidden ${featured ? "border-maroon ring-2 ring-maroon/10" : "border-gold/35"}`}>
      <div className={`${featured ? "brand-gradient" : "bg-sand"} temple-silhouette px-6 py-6 ${featured ? "text-white" : "text-ink"}`}>
        <p className={`text-xs font-extrabold uppercase tracking-widest ${featured ? "text-gold" : "text-saffron"}`}>{stay.bestFor}</p>
        <h3 className={`mt-2 font-serif text-3xl ${featured ? "text-white" : "text-ink"}`}>Stay in {stay.city}</h3>
      </div>
      <CardContent>
        <p className="text-sm leading-6 text-stone-600">{stay.description}</p>
        <ul className="mt-5 space-y-3">{stay.points.map((point) => <li key={point} className="flex gap-2 text-sm text-stone-700"><Check className="mt-0.5 h-4 w-4 shrink-0 text-saffron" />{point}</li>)}</ul>
        <Button asChild variant="outline" className="mt-6 w-full"><Link href="/stay-guide">Compare stays <ArrowRight className="h-4 w-4" /></Link></Button>
      </CardContent>
    </Card>
  );
}

export function HomeFinalCTA() {
  return (
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="brand-gradient temple-silhouette relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] border border-gold/40 p-8 text-center text-white shadow-soft sm:p-12">
        <div className="pattern-mandala absolute inset-0 opacity-15" />
        <div className="relative">
          <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-gold">A simpler starting point</p>
          <h2 className="text-balance mx-auto mt-4 max-w-3xl font-serif text-3xl text-white sm:text-5xl">Not sure where to stay or how many days are enough?</h2>
          <p className="mx-auto mt-4 max-w-xl leading-7 text-orange-50/75">Tell us who is travelling, your pace and the places you want to add. Get a practical itinerary in minutes.</p>
          <Button asChild size="lg" className="mt-7 bg-white text-maroon hover:bg-orange-50"><Link href="/plan-my-trip">Plan My Trip <ArrowRight className="h-4 w-4" /></Link></Button>
        </div>
      </div>
    </section>
  );
}
