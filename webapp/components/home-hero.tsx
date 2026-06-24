import Image from "next/image";
import Link from "next/link";
import {
  BedDouble,
  Landmark,
  MapPin,
  Plane,
  Route,
  Users,
} from "lucide-react";
import { MotionReveal } from "./motion-reveal";
import { Button } from "./ui/button";
import { WhatsAppShareButton } from "./travel-components";

const floatingCards = [
  { label: "Mahakal Darshan", meta: "Temple guide", icon: Landmark, position: "lg:left-[58%] lg:top-[18%]" },
  { label: "Indore Airport", meta: "55 km to Ujjain", icon: Plane, position: "lg:right-[6%] lg:top-[35%]" },
  { label: "Omkareshwar Trip", meta: "Second Jyotirlinga", icon: Route, position: "lg:left-[61%] lg:bottom-[16%]" },
  { label: "Family Stay Guide", meta: "3-city comparison", icon: Users, position: "lg:right-[3%] lg:bottom-[7%]" },
];

export function HomeHero() {
  return (
    <section className="temple-silhouette relative overflow-hidden bg-[#351013] text-white">
      <Image
        src="/images/mahakal-ghat-temple.png"
        alt="Devotees gathered beside the temple ghats in Ujjain at sunset"
        fill
        priority
        className="object-cover object-[62%_center] sm:object-center"
        sizes="100vw"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-[#210b0d]/95 via-[#55191d]/80 to-[#6e2024]/25" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#260d0f]/85 via-transparent to-black/20" />
      <div className="pattern-mandala absolute inset-0 opacity-10" />
      <div className="relative mx-auto grid min-h-[720px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:grid-cols-[1.08fr_.92fr] lg:px-8">
        <MotionReveal className="relative z-10 max-w-3xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.2em] text-[#ffd28a] backdrop-blur">
            <MapPin className="h-4 w-4" /> Ujjain Kumbh Mela 2028
          </p>
          <h1 className="text-balance mt-6 font-serif text-5xl leading-[1.02] text-white sm:text-6xl lg:text-[4.8rem]">
            Plan Your Ujjain Kumbh Mela 2028 Journey
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-orange-50/85 sm:text-xl sm:leading-8">
            Your complete guide for Mahakal Darshan, stay, travel routes, food, nearby Jyotirlinga trips, and family-friendly itineraries.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <Button asChild size="lg"><Link href="/plan-my-trip">Plan My Trip</Link></Button>
            <Button asChild variant="outline" size="lg"><Link href="/mahakal-temple-guide"><Landmark className="h-4 w-4" />Explore Mahakal Guide</Link></Button>
            <Button asChild variant="outline" size="lg"><Link href="/stay-guide"><BedDouble className="h-4 w-4" />Stay Options</Link></Button>
          </div>
          <div className="mt-5"><WhatsAppShareButton text="Plan your Ujjain Kumbh Mela 2028 journey with this complete Mahakal travel guide: https://ujjain2028.in" /></div>
        </MotionReveal>

        <div className="relative mt-12 grid grid-cols-2 gap-3 lg:mt-0 lg:h-[520px]">
          <div className="absolute inset-12 hidden rounded-full border border-gold/20 lg:block" />
          <div className="absolute inset-24 hidden rounded-full border border-white/10 lg:block" />
          {floatingCards.map(({ label, meta, icon: Icon, position }, index) => (
            <MotionReveal key={label} delay={index * 0.08} className={`relative z-10 lg:absolute ${position}`}>
              <div className="min-h-32 rounded-2xl border border-white/35 bg-white/90 p-4 text-ink shadow-2xl shadow-black/30 backdrop-blur-md sm:min-w-48">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-orange-50 text-saffron"><Icon className="h-5 w-5" /></span>
                <p className="mt-4 text-sm font-extrabold">{label}</p>
                <p className="mt-1 text-xs text-stone-500">{meta}</p>
              </div>
            </MotionReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
