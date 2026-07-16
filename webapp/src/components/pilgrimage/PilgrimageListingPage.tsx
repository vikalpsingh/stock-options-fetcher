import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PilgrimageHero, OfficialDisclaimer, PackageCTA, SectionTitle } from "./PilgrimageTemplates";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";

export function PilgrimageListingPage({ eyebrow, title, subtitle, cards, sourcePage }: { eyebrow: string; title: string; subtitle: string; sourcePage: string; cards: { title: string; description: string; href: string; badge?: string }[] }) {
  return <main><PilgrimageHero eyebrow={eyebrow} title={title} subtitle={subtitle} primaryLabel="Use travel tools" primaryHref="/travel-tools" secondaryLabel="Get package quote" secondaryHref="/packages" /><OfficialDisclaimer /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Guides" title={`Explore ${title}`} text="Start with practical guidance, then verify official details before booking." /><div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{cards.map((card) => <Link key={card.href} href={card.href} className="group"><Card className="h-full border-gold/35 transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{card.badge || "Guide"}</p><h2 className="mt-3 font-serif text-2xl">{card.title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{card.description}</p><span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">Open guide<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>)}</div></div></section><section className="bg-white px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><TravelSearchWidget title="Search travel for this yatra" sourcePage={sourcePage} /></div></section><PackageCTA /></main>;
}
