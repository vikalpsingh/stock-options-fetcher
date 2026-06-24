"use client";

import { useEffect, useState } from "react";
import {
  Accessibility,
  AlertTriangle,
  ArrowRight,
  Baby,
  BedDouble,
  BusFront,
  Check,
  Clock3,
  Footprints,
  HeartHandshake,
  MapPin,
  MoonStar,
  Navigation,
  ShieldCheck,
  Soup,
  Sparkles,
  SunMedium,
  Users,
} from "lucide-react";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { cn } from "@/lib/utils";

export function ElderlyFriendlyBadge({ label = "Elderly-friendly option" }: { label?: string }) {
  return <span className="inline-flex items-center gap-1.5 rounded-full border border-[#398266]/25 bg-[#eaf7f0] px-3 py-1.5 text-xs font-bold text-[#24664e]"><Accessibility className="h-3.5 w-3.5" />{label}</span>;
}

export function WeekendCrowdWarningBadge({ label = "Weekend crowds: high" }: { label?: string }) {
  return <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/70 bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-800"><AlertTriangle className="h-3.5 w-3.5" />{label}</span>;
}

export function KumbhCountdownCard() {
  const [days, setDays] = useState(0);
  useEffect(() => {
    const target = new Date("2028-04-01T00:00:00+05:30").getTime();
    setDays(Math.max(0, Math.ceil((target - Date.now()) / 86400000)));
  }, []);
  const years = Math.floor(days / 365);
  const remainingDays = days % 365;

  return (
    <Card className="brand-gradient temple-silhouette overflow-hidden border-gold/50 text-white">
      <CardContent className="relative p-7 sm:p-9">
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-[#ffd58f]">Planning countdown</p>
            <h3 className="mt-3 max-w-lg font-serif text-3xl text-white sm:text-4xl">Begin preparing for Ujjain Kumbh 2028</h3>
          </div>
          <MoonStar className="hidden h-10 w-10 text-gold sm:block" />
        </div>
        <div className="mt-7 flex gap-3">
          <CountdownUnit value={years} label="Years" />
          <CountdownUnit value={remainingDays} label="Days" />
        </div>
        <p className="mt-6 max-w-xl text-xs leading-5 text-orange-50/70">Countdown uses April 1, 2028 as a planning milestone—not an official opening date. Confirm all dates before booking.</p>
      </CardContent>
    </Card>
  );
}

function CountdownUnit({ value, label }: { value: number; label: string }) {
  return <div className="min-w-24 rounded-2xl border border-white/15 bg-black/15 p-4 text-center backdrop-blur"><strong className="block text-3xl">{value}</strong><span className="text-[10px] font-bold uppercase tracking-widest text-orange-50/70">{label}</span></div>;
}

export function TravelRouteCard({ from, distance, duration, mode, tip }: { from: string; distance: string; duration: string; mode: string; tip: string }) {
  return (
    <Card className="h-full border-l-4 border-l-saffron">
      <CardContent>
        <div className="flex items-start justify-between gap-3"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-orange-50 text-saffron"><BusFront className="h-5 w-5" /></span><span className="rounded-full bg-sand px-3 py-1 text-xs font-bold text-maroon">{distance}</span></div>
        <h3 className="mt-5 font-serif text-xl">From {from}</h3>
        <div className="mt-4 flex items-center gap-4 text-xs font-semibold text-stone-500"><span className="flex items-center gap-1"><Clock3 className="h-4 w-4 text-saffron" />{duration}</span><span>{mode}</span></div>
        <p className="mt-4 border-t border-stone-200 pt-4 text-sm leading-6 text-stone-600">{tip}</p>
        <Button asChild variant="outline" size="sm" className="mt-5"><a href={`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(from)}&destination=Ujjain`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" />View route</a></Button>
      </CardContent>
    </Card>
  );
}

export function TempleDarshanCard() {
  return (
    <Card className="overflow-hidden border-gold/50">
      <div className="brand-gradient temple-silhouette min-h-40 p-6 text-white">
        <div className="flex justify-between"><span className="grid h-12 w-12 place-items-center rounded-full border border-gold/50 bg-black/15 text-2xl text-gold">ॐ</span><WeekendCrowdWarningBadge /></div>
        <h3 className="mt-6 font-serif text-3xl text-white">Mahakal Darshan</h3>
      </div>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 text-sm"><Info icon={SunMedium} label="Best time" value="Early morning" /><Info icon={Clock3} label="Keep aside" value="2–4 hours" /></div>
        <div className="mt-5"><ElderlyFriendlyBadge label="Assisted access guidance" /></div>
        <p className="mt-4 text-sm leading-6 text-stone-600">Keep original ID, use official booking channels and plan a rest window after darshan.</p>
      </CardContent>
    </Card>
  );
}

function Info({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return <div className="rounded-xl bg-sand/70 p-3"><Icon className="h-4 w-4 text-saffron" /><span className="mt-2 block text-[10px] font-bold uppercase tracking-wider text-stone-500">{label}</span><strong className="mt-1 block text-xs text-ink">{value}</strong></div>;
}

type Stay = { city: string; tag: string; travel: string; budget: string; pros: string[]; recommendedFor: string };
export function StayComparisonTable({ stays }: { stays: Stay[] }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-gold/40 bg-white shadow-soft">
      <div className="hidden grid-cols-[1.1fr_1fr_1fr_1.8fr] bg-maroon px-6 py-4 text-xs font-bold uppercase tracking-wider text-white md:grid">
        <span>City</span><span>Travel</span><span>Typical budget</span><span>Best suited for</span>
      </div>
      <div className="divide-y divide-stone-200">
        {stays.map((stay, index) => (
          <div key={stay.city} className={cn("grid gap-4 p-5 md:grid-cols-[1.1fr_1fr_1fr_1.8fr] md:items-center md:px-6", index === 0 && "bg-orange-50/35")}>
            <div><div className="flex flex-wrap items-center gap-2"><strong className="font-serif text-xl">{stay.city}</strong>{index === 0 && <ElderlyFriendlyBadge label="Best for early darshan" />}</div><p className="mt-1 text-xs font-semibold text-saffron">{stay.tag}</p></div>
            <TableValue label="Travel">{stay.travel}</TableValue>
            <TableValue label="Budget">{stay.budget}</TableValue>
            <TableValue label="Best for">{stay.recommendedFor}</TableValue>
          </div>
        ))}
      </div>
    </div>
  );
}

function TableValue({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-stone-400 md:hidden">{label}</span><span className="text-sm leading-6 text-stone-600">{children}</span></div>;
}

export function DestinationTimelineCard({ destinations }: { destinations: { name: string; distance: string; duration: string; description: string }[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="brand-gradient temple-silhouette px-6 py-7 text-white"><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">A comfortable extension</p><h3 className="mt-2 font-serif text-3xl text-white">Sacred Malwa timeline</h3></div>
      <CardContent>
        <ol className="relative ml-3 border-l border-gold/50 pl-7">
          {destinations.slice(0, 4).map((item, index) => <li key={item.name} className="relative pb-7 last:pb-0"><span className="absolute -left-[37px] grid h-5 w-5 place-items-center rounded-full bg-saffron text-[9px] font-bold text-white ring-4 ring-orange-50">{index + 1}</span><div className="flex flex-wrap items-baseline justify-between gap-2"><h4 className="font-serif text-lg">{item.name}</h4><span className="text-xs font-bold text-saffron">{item.distance} · {item.duration}</span></div><p className="mt-2 text-sm leading-6 text-stone-600">{item.description}</p></li>)}
        </ol>
      </CardContent>
    </Card>
  );
}

export function FoodDiscoveryCard({ foods }: { foods: { name: string; category: string; bestTime: string }[] }) {
  return (
    <Card className="h-full border-t-4 border-t-saffron">
      <CardContent>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Soup className="h-6 w-6" /></span>
        <h3 className="mt-5 font-serif text-2xl">A day of Malwa flavours</h3>
        <div className="mt-5 space-y-4">{foods.slice(0, 4).map((food, index) => <div key={food.name} className="flex gap-3"><span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-gold ring-4 ring-orange-50" /><div><p className="text-sm font-bold">{food.name}</p><p className="text-xs text-stone-500">{food.category} · {food.bestTime}</p></div></div>)}</div>
        <Button asChild variant="outline" className="mt-6 w-full"><a href="/food-guide">Explore food guide <ArrowRight className="h-4 w-4" /></a></Button>
      </CardContent>
    </Card>
  );
}

export function FamilyTravelTipsCard() {
  const tips = [
    [Users, "Set a meeting point", "Crowds can interrupt mobile networks."],
    [Accessibility, "Plan fewer stops", "One major darshan plus rest is enough for elders."],
    [Baby, "Carry a family day bag", "Water, snacks, medicines and ID copies."],
    [ShieldCheck, "Use official help desks", "Avoid agents and unverified shortcuts."],
  ] as const;
  return (
    <Card className="h-full bg-[#fffaf0] border-gold/40">
      <CardContent>
        <div className="flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-full bg-maroon text-gold"><HeartHandshake className="h-6 w-6" /></span><div><p className="text-xs font-bold uppercase tracking-widest text-saffron">Family travel</p><h3 className="font-serif text-2xl">Comfort before checklists</h3></div></div>
        <div className="mt-6 space-y-5">{tips.map(([Icon, title, text]) => <div key={title} className="flex gap-3"><Icon className="mt-0.5 h-5 w-5 shrink-0 text-saffron" /><div><p className="text-sm font-bold">{title}</p><p className="mt-1 text-xs leading-5 text-stone-600">{text}</p></div></div>)}</div>
        <div className="mt-6 flex flex-wrap gap-2"><ElderlyFriendlyBadge /><WeekendCrowdWarningBadge /></div>
      </CardContent>
    </Card>
  );
}
