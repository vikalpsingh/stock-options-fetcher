import Image from "next/image";
import Link from "next/link";
import { BedDouble, BusFront, CalendarDays, Landmark, MapPin, MapPinned, Soup } from "lucide-react";
import type { LocaleCode } from "@/lib/locale";
import { uiCopy } from "@/data/locale-ui";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

const icons = [Landmark, BusFront, BedDouble, MapPinned, CalendarDays, Soup];
const paths = ["/mahakal-temple-guide", "/how-to-reach", "/stay-guide", "/nearby-places", "/itineraries", "/food-guide"];

export function HindiHome({ locale }: { locale: LocaleCode }) {
  const copy = uiCopy[locale];
  return <main>
    <section className="temple-silhouette relative min-h-[700px] overflow-hidden bg-maroon text-white">
      <Image src="/images/mahakal-ghat-temple.png" alt={copy.siteName} fill priority className="object-cover object-[62%_center] sm:object-center" sizes="100vw" />
      <div className="absolute inset-0 bg-gradient-to-r from-[#210b0d]/95 via-[#55191d]/82 to-[#6e2024]/30" /><div className="absolute inset-0 bg-gradient-to-t from-[#260d0f]/85 via-transparent to-black/20" /><div className="pattern-mandala absolute inset-0 opacity-10" />
      <div className="relative mx-auto flex min-h-[700px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:px-8"><div className="max-w-4xl">
        <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/20 px-4 py-2 text-xs font-bold text-gold"><MapPin className="h-4 w-4" />{copy.homeEyebrow}</p>
        <h1 className="mt-6 font-serif text-5xl font-semibold leading-[1.08] sm:text-6xl lg:text-7xl">{copy.homeTitle}</h1><p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{copy.homeDescription}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap"><Button asChild size="lg"><Link href={`/${locale}/plan-my-trip`}>{copy.planTrip}</Link></Button><Button asChild variant="outline" size="lg"><Link href={`/${locale}/mahakal-temple-guide`}>{copy.heroMahakal}</Link></Button><Button asChild variant="outline" size="lg"><Link href={`/${locale}/stay-guide`}>{copy.heroStay}</Link></Button></div>
      </div></div>
    </section>
    <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
      <p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.startHere}</p><h2 className="mt-3 max-w-3xl font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{copy.sectionTitle}</h2><p className="mt-4 max-w-3xl text-lg leading-8 text-stone-600">{copy.sectionDescription}</p>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{paths.map((path, index) => { const Icon = icons[index]; return <Link key={path} href={`/${locale}${path}`} className="group"><Card className="premium-card h-full transition group-hover:-translate-y-1 group-hover:border-saffron/50"><CardContent><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span><h3 className="mt-5 font-serif text-2xl">{copy.nav[[1, 3, 2, 4, 5, 6][index]]}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{copy.sectionDescription}</p><span className="mt-5 inline-block text-sm font-bold text-maroon">{copy.readMore}</span></CardContent></Card></Link>; })}</div>
    </div></section>
    <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-6xl rounded-[2rem] bg-maroon p-8 text-white sm:p-12"><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">{copy.finalEyebrow}</p><h2 className="mt-3 max-w-3xl font-serif text-4xl">{copy.finalTitle}</h2><p className="mt-4 max-w-2xl leading-7 text-orange-50/80">{copy.finalText}</p><Button asChild size="lg" className="mt-7"><Link href={`/${locale}/plan-my-trip`}>{copy.openPlanner}</Link></Button></div></section>
  </main>;
}
