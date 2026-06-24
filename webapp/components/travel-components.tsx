import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  Clock3,
  ExternalLink,
  HeartHandshake,
  MapPinned,
  MessageCircle,
  Navigation,
  ShieldCheck,
  Sparkles,
  Star,
  Users,
  Utensils,
} from "lucide-react";
import { MotionReveal } from "./motion-reveal";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { cn } from "@/lib/utils";

export function HeroSection({
  eyebrow,
  title,
  accent,
  description,
  primaryHref = "/plan-my-trip",
  compact = false,
}: {
  eyebrow: string;
  title: string;
  accent?: string;
  description: string;
  primaryHref?: string;
  compact?: boolean;
}) {
  return (
    <section className={cn("relative overflow-hidden bg-[#241412] text-white", compact ? "py-16 sm:py-20" : "min-h-[700px]")}>
      {!compact && <Image src="/images/ujjain-shipra-hero.png" alt="Ujjain temple ghats at sunrise" fill priority className="object-cover object-center" sizes="100vw" />}
      <div className="absolute inset-0 bg-gradient-to-r from-[#1b0d0b]/95 via-[#3b1717]/78 to-[#5a2416]/30" />
      <div className="pattern-mandala absolute inset-0 opacity-15" />
      <div className="temple-silhouette absolute inset-x-0 bottom-0 h-44" />
      <div className={cn("relative mx-auto flex max-w-7xl items-center px-4 sm:px-6 lg:px-8", compact ? "" : "min-h-[700px] py-20")}>
        <MotionReveal className="max-w-3xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-gold/35 bg-black/15 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#f5c985] backdrop-blur">
            <Sparkles className="h-4 w-4" /> {eyebrow}
          </p>
          <h1 className={cn("mt-6 font-serif font-semibold leading-[1.02]", compact ? "text-4xl sm:text-6xl" : "text-5xl sm:text-7xl lg:text-[5.4rem]")}>
            {title} {accent && <span className="text-[#f4b765]">{accent}</span>}
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-orange-50/80 sm:text-xl sm:leading-8">{description}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg"><Link href={primaryHref}>Plan my trip <ArrowRight className="h-4 w-4" /></Link></Button>
            <GoogleMapButton label="Route to Ujjain" />
          </div>
        </MotionReveal>
      </div>
    </section>
  );
}

export function SectionTitle({ eyebrow, title, description, center = false }: { eyebrow: string; title: string; description?: string; center?: boolean }) {
  return (
    <div className={cn("max-w-2xl", center && "mx-auto text-center")}>
      <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-saffron">{eyebrow}</p>
      <h2 className="mt-3 font-serif text-3xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2>
      {description && <p className="mt-4 leading-7 text-stone-600 sm:text-lg">{description}</p>}
    </div>
  );
}

export function FeatureCard({ icon: Icon, title, description, href }: { icon: React.ComponentType<{ className?: string }>; title: string; description: string; href: string }) {
  return (
    <MotionReveal>
      <Link href={href} className="group block h-full">
        <Card className="h-full transition duration-300 hover:-translate-y-1 hover:border-saffron/40 hover:shadow-soft">
          <CardContent>
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span>
            <h3 className="mt-6 font-serif text-2xl font-semibold text-ink">{title}</h3>
            <p className="mt-3 text-sm leading-6 text-stone-600">{description}</p>
            <span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">View guide <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span>
          </CardContent>
        </Card>
      </Link>
    </MotionReveal>
  );
}

export function DestinationCard({ destination }: { destination: { name: string; distance: string; duration: string; description: string; highlights: string[]; tone: string } }) {
  return (
    <Card className="group h-full overflow-hidden">
      <div className={cn("relative h-40 overflow-hidden bg-gradient-to-br p-6", destination.tone === "maroon" ? "from-maroon to-[#321013]" : destination.tone === "gold" ? "from-[#a8742e] to-[#5b3515]" : destination.tone === "ink" ? "from-ink to-stone-700" : "from-saffron to-[#963815]")}>
        <div className="pattern-arches absolute inset-0 opacity-25" />
        <MapPinned className="relative h-8 w-8 text-white/80" />
        <h3 className="relative mt-5 font-serif text-3xl font-semibold text-white">{destination.name}</h3>
      </div>
      <CardContent>
        <div className="flex gap-4 text-xs font-bold uppercase tracking-wider text-saffron"><span>{destination.distance}</span><span>{destination.duration}</span></div>
        <p className="mt-4 text-sm leading-6 text-stone-600">{destination.description}</p>
        <div className="mt-5 flex flex-wrap gap-2">{destination.highlights.map((item) => <span key={item} className="rounded-full bg-sand px-3 py-1.5 text-xs font-semibold text-stone-700">{item}</span>)}</div>
        <div className="mt-6 flex gap-2"><GoogleMapButton destination={destination.name} compact /><WhatsAppShareButton text={`Add ${destination.name} to your Ujjain 2028 trip`} compact /></div>
      </CardContent>
    </Card>
  );
}

export function ItineraryCard({ itinerary }: { itinerary: { title: string; days: number; audience: string; summary: string; schedule: string[] } }) {
  return (
    <Card className="h-full overflow-hidden">
      <div className="border-b border-stone-200 bg-sand/60 px-6 py-5">
        <div className="flex items-center justify-between gap-3"><span className="rounded-full bg-maroon px-3 py-1 text-xs font-bold text-white">{itinerary.days} days</span><span className="text-xs font-semibold text-stone-500">{itinerary.audience}</span></div>
        <h3 className="mt-4 font-serif text-2xl font-semibold text-ink">{itinerary.title}</h3>
        <p className="mt-2 text-sm leading-6 text-stone-600">{itinerary.summary}</p>
      </div>
      <CardContent>
        <ol className="space-y-4">{itinerary.schedule.map((day, index) => <li key={day} className="flex gap-3 text-sm leading-6 text-stone-700"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-orange-50 text-xs font-bold text-saffron">{index + 1}</span>{day}</li>)}</ol>
        <div className="mt-6 flex flex-wrap gap-2"><PrintButton /><WhatsAppShareButton text={`${itinerary.title}: ${itinerary.schedule.join("; ")}`} compact /></div>
      </CardContent>
    </Card>
  );
}

export function TempleCard({ temple, showActions = false }: { temple: { name: string; subtitle: string; description?: string; bestTime: string; duration: string; familyTip: string; familySuitability?: string; highlights: string[]; mapsQuery?: string }; showActions?: boolean }) {
  return (
    <Card className="h-full border-t-4 border-t-gold">
      <CardContent>
        <div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-full bg-maroon text-xl text-gold">ॐ</span><Star className="h-5 w-5 fill-gold text-gold" /></div>
        <h3 className="mt-5 font-serif text-2xl font-semibold text-ink">{temple.name}</h3>
        <p className="mt-1 text-sm font-semibold text-saffron">{temple.subtitle}</p>
        {temple.description && <p className="mt-3 text-sm leading-6 text-stone-600">{temple.description}</p>}
        <div className="mt-5 grid grid-cols-2 gap-3 rounded-2xl bg-sand/70 p-4 text-xs"><span><Clock3 className="mb-1 h-4 w-4 text-maroon" />{temple.bestTime}</span><span><Users className="mb-1 h-4 w-4 text-maroon" />{temple.duration}</span></div>
        <p className="mt-4 text-sm leading-6 text-stone-600"><strong>Family note:</strong> {temple.familyTip}</p>
        {temple.familySuitability && <p className="mt-3 inline-flex rounded-full bg-[#eaf7f0] px-3 py-1.5 text-xs font-bold text-[#24664e]">{temple.familySuitability}</p>}
        <div className="mt-4 flex flex-wrap gap-2">{temple.highlights.map((item) => <span key={item} className="rounded-full border border-stone-200 px-3 py-1 text-xs text-stone-600">{item}</span>)}</div>
        {showActions && <div className="mt-6 grid grid-cols-2 gap-2"><GoogleMapButton destination={temple.mapsQuery || `${temple.name}, Ujjain`} compact /><Button asChild variant="maroon" size="sm"><Link href={`/plan-my-trip?add=${encodeURIComponent(temple.name)}`}>Add to itinerary</Link></Button></div>}
      </CardContent>
    </Card>
  );
}

export function StayComparisonCard({ stay, featured = false }: { stay: { city: string; tag: string; travel: string; budget: string; pros: string[]; cons: string[]; recommendedFor: string }; featured?: boolean }) {
  return (
    <Card className={cn("relative h-full", featured && "border-maroon ring-2 ring-maroon/10")}>
      {featured && <span className="absolute right-5 top-0 -translate-y-1/2 rounded-full bg-maroon px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-white">Family favourite</span>}
      <CardContent>
        <p className="text-xs font-bold uppercase tracking-widest text-saffron">{stay.tag}</p>
        <h3 className="mt-2 font-serif text-3xl font-semibold text-ink">{stay.city}</h3>
        <div className="mt-5 grid grid-cols-2 gap-3 rounded-2xl bg-sand/60 p-4 text-sm"><span><strong className="block text-xs text-stone-500">Travel</strong>{stay.travel}</span><span><strong className="block text-xs text-stone-500">Typical range</strong>{stay.budget}</span></div>
        <p className="mt-5 text-sm font-bold text-ink">Why it works</p>
        <ul className="mt-3 space-y-2">{stay.pros.map((item) => <li key={item} className="flex gap-2 text-sm text-stone-600"><Check className="h-4 w-4 shrink-0 text-[#168f4d]" />{item}</li>)}</ul>
        <p className="mt-5 text-xs leading-5 text-stone-500"><strong>Best for:</strong> {stay.recommendedFor}</p>
      </CardContent>
    </Card>
  );
}

export function FoodCard({ food }: { food: { name: string; category: string; description: string; diet: string; bestTime: string } }) {
  return (
    <Card className="h-full">
      <CardContent>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Utensils className="h-6 w-6" /></span>
        <p className="mt-5 text-xs font-bold uppercase tracking-widest text-saffron">{food.category}</p>
        <h3 className="mt-2 font-serif text-2xl font-semibold text-ink">{food.name}</h3>
        <p className="mt-3 text-sm leading-6 text-stone-600">{food.description}</p>
        <div className="mt-5 flex items-center justify-between border-t border-stone-200 pt-4 text-xs font-semibold text-stone-500"><span>{food.diet}</span><span>{food.bestTime}</span></div>
      </CardContent>
    </Card>
  );
}

export function WhatsAppShareButton({ text, compact = false }: { text: string; compact?: boolean }) {
  return <Button asChild variant="whatsapp" size={compact ? "sm" : "default"}><a href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4" />{compact ? "Share" : "Share on WhatsApp"}</a></Button>;
}

export function GoogleMapButton({ destination = "Ujjain, Madhya Pradesh", label = "Open in Maps", compact = false }: { destination?: string; label?: string; compact?: boolean }) {
  return <Button asChild variant="outline" size={compact ? "sm" : "lg"}><a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" />{compact ? "Map" : label}<ExternalLink className="h-3 w-3" /></a></Button>;
}

export function PrintButton() {
  return <Button asChild variant="outline" size="sm"><Link href="/plan-my-trip#print-itinerary">Print / save</Link></Button>;
}

export function TrustBanner() {
  return (
    <section className="border-y border-stone-200 bg-white">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-5 px-4 py-7 sm:px-6 lg:grid-cols-4 lg:px-8">
        {[
          [ShieldCheck, "Practical & verified", "Official sources first"],
          [HeartHandshake, "Family-focused", "Parents and children"],
          [Navigation, "Route-ready", "Direct Maps links"],
          [Sparkles, "Spiritual, not stressful", "Calm trip planning"],
        ].map(([Icon, title, text]) => {
          const ItemIcon = Icon as typeof ShieldCheck;
          return <div key={String(title)} className="flex gap-3"><ItemIcon className="h-6 w-6 shrink-0 text-saffron" /><div><p className="text-sm font-bold text-ink">{String(title)}</p><p className="text-xs text-stone-500">{String(text)}</p></div></div>;
        })}
      </div>
    </section>
  );
}
