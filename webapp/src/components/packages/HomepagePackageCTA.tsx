import Link from "next/link";
import { ArrowRight, BedDouble, Building2, HeartHandshake, Landmark, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const packageCards = [
  { title: "Ujjain Kumbh 2028 Packages", text: "Family, darshan, stay and transport options.", icon: Landmark },
  { title: "Senior Citizen Assisted Yatra", text: "Slower pacing and accessibility requirements.", icon: HeartHandshake },
  { title: "Indore Stay + Ujjain Day Trip", text: "Airport access with an early Ujjain transfer.", icon: BedDouble },
  { title: "Group / Society Kumbh Package", text: "Rooms, vehicles and coordinated group planning.", icon: Users },
];

export function HomepagePackageCTA() {
  return (
    <section className="pattern-mandala bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-8 lg:grid-cols-[.8fr_1.2fr] lg:items-end">
          <div>
            <p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Package discovery</p>
            <h2 className="mt-3 font-serif text-4xl font-semibold leading-tight sm:text-5xl">Plan Your Kumbh Yatra with Verified Travel Partners</h2>
          </div>
          <p className="text-lg leading-8 text-stone-600">From Mahakal darshan to family stay, local transport and senior citizen support, IndianKumbh.com helps you compare practical pilgrimage package options for Ujjain Simhastha 2028 and other Kumbh destinations.</p>
        </div>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {packageCards.map(({ icon: Icon, ...card }) => <Card key={card.title} className="h-full border-gold/35"><CardContent><Icon className="h-6 w-6 text-saffron" /><h3 className="mt-5 font-serif text-xl">{card.title}</h3><p className="mt-3 text-sm leading-6 text-stone-600">{card.text}</p></CardContent></Card>)}
        </div>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button asChild size="lg"><Link href="/ujjain-kumbh-2028/packages">Get Ujjain Package Quote<ArrowRight className="h-4 w-4" /></Link></Button>
          <Button asChild variant="outline"><Link href="/go/booking?city=ujjain&campaign=ujjain-kumbh-2028&sourcePage=home-package-cta"><BedDouble className="h-4 w-4" />Check Ujjain Hotels</Link></Button>
          <Button asChild variant="outline"><Link href="/go/booking?city=indore&campaign=ujjain-kumbh-2028&sourcePage=home-package-cta"><Building2 className="h-4 w-4" />Check Indore Hotels</Link></Button>
        </div>
        <p className="mt-5 text-xs leading-5 text-stone-500">Packages are fulfilled by independent travel partners. IndianKumbh.com does not operate tours directly.</p>
      </div>
    </section>
  );
}
