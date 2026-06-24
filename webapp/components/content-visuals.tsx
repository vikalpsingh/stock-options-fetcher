import Link from "next/link";
import {
  CalendarDays,
  Car,
  Clock,
  HeartHandshake,
  Hotel,
  Languages,
  Leaf,
  MapPin,
  Plane,
  Share2,
  Sparkles,
  Train,
  Utensils,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

export type TravelBadgeKind =
  | "Family Friendly"
  | "Elderly Friendly"
  | "Day Trip"
  | "Spiritual"
  | "Food"
  | "Heritage"
  | "Nature";

const badgeStyles: Record<TravelBadgeKind, { icon: typeof MapPin; className: string }> = {
  "Family Friendly": { icon: HeartHandshake, className: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  "Elderly Friendly": { icon: HeartHandshake, className: "border-teal-200 bg-teal-50 text-teal-800" },
  "Day Trip": { icon: CalendarDays, className: "border-orange-200 bg-orange-50 text-orange-800" },
  Spiritual: { icon: Sparkles, className: "border-amber-200 bg-amber-50 text-amber-900" },
  Food: { icon: Utensils, className: "border-rose-200 bg-rose-50 text-rose-800" },
  Heritage: { icon: Hotel, className: "border-yellow-200 bg-yellow-50 text-yellow-900" },
  Nature: { icon: Leaf, className: "border-green-200 bg-green-50 text-green-800" },
};

export function TravelBadge({ kind }: { kind: TravelBadgeKind }) {
  const style = badgeStyles[kind];
  const Icon = style.icon;
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-bold", style.className)}><Icon className="h-3.5 w-3.5" />{kind}</span>;
}

type Route = {
  name: string;
  shortDescription: string;
  from: string;
  to: string;
  mode: string;
  travelTimePlaceholder: string;
  mapSearchQuery: string;
  bestFor: string[];
  tags: string[];
};

export function IllustratedRouteCard({ route }: { route: Route }) {
  const mode = route.mode.toLowerCase();
  const ModeIcon = mode.includes("plane") || mode.includes("flight") ? Plane : mode.includes("train") ? Train : Car;
  return (
    <Card className="premium-card group h-full overflow-hidden">
      <div className="brand-gradient route-grid relative min-h-40 overflow-hidden p-6 text-white">
        <div className="pattern-jaali absolute inset-0 opacity-25" />
        <div className="relative flex items-start justify-between">
          <span className="grid h-12 w-12 place-items-center rounded-2xl border border-white/20 bg-black/15 backdrop-blur"><ModeIcon className="h-6 w-6 text-gold" /></span>
          <span className="rounded-full border border-white/20 bg-black/15 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-orange-50">{route.mode}</span>
        </div>
        <div className="relative mt-7 flex items-center gap-3">
          <MapPin className="map-pin-glow h-7 w-7 shrink-0 fill-gold text-gold" />
          <div><p className="text-xs text-orange-100">{route.from} → {route.to}</p><h3 className="mt-1 font-serif text-2xl text-white">{route.name}</h3></div>
        </div>
      </div>
      <CardContent>
        <p className="text-sm leading-6 text-stone-600">{route.shortDescription}</p>
        <div className="mt-5 flex items-center gap-2 rounded-2xl bg-sand/65 p-4 text-xs font-semibold text-stone-700"><Clock className="h-4 w-4 text-saffron" />{route.travelTimePlaceholder}</div>
        <div className="mt-5 flex flex-wrap gap-2">
          {route.tags.filter((tag): tag is TravelBadgeKind => tag in badgeStyles).slice(0, 2).map((tag) => <TravelBadge key={tag} kind={tag} />)}
        </div>
        <Button asChild variant="outline" className="mt-6 w-full">
          <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(route.mapSearchQuery)}`} target="_blank" rel="noreferrer"><MapPin className="h-4 w-4" />Open route map</a>
        </Button>
      </CardContent>
    </Card>
  );
}

export function RoutePlanningTimeline() {
  const steps = [
    { icon: Languages, title: "Confirm current advisories", text: "Check official transport and Kumbh traffic updates before departure." },
    { icon: Clock, title: "Add a crowd buffer", text: "Published travel times are planning placeholders, especially on major event days." },
    { icon: MapPin, title: "Save your drop point", text: "Traffic controls may require walking or a shuttle for the final stretch." },
    { icon: Share2, title: "Share the route", text: "Send the map and meeting point to every adult in the group." },
  ];
  return (
    <Card className="premium-card overflow-hidden">
      <div className="brand-gradient temple-silhouette px-6 py-8 text-white">
        <p className="text-xs font-bold uppercase tracking-[.2em] text-gold">A calmer arrival</p>
        <h2 className="mt-2 font-serif text-3xl text-white">Four checks before you leave</h2>
      </div>
      <CardContent>
        <ol className="relative ml-5 border-l border-gold/50 pl-8">
          {steps.map(({ icon: Icon, title, text }, index) => (
            <li key={title} className="relative pb-8 last:pb-0">
              <span className="absolute -left-[49px] grid h-8 w-8 place-items-center rounded-full bg-maroon text-gold ring-4 ring-cream"><Icon className="h-4 w-4" /></span>
              <p className="text-xs font-bold uppercase tracking-wider text-saffron">Step {index + 1}</p>
              <h3 className="mt-1 font-bold text-ink">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-stone-600">{text}</p>
            </li>
          ))}
        </ol>
        <Button asChild className="mt-7 w-full sm:w-auto"><Link href="/plan-my-trip">Build my travel plan</Link></Button>
      </CardContent>
    </Card>
  );
}
