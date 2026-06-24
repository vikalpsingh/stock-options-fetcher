"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Check,
  Clock3,
  HeartHandshake,
  MapPin,
  MessageCircle,
  Navigation,
  Plus,
  Route,
  Sparkles,
  X,
} from "lucide-react";
import guide from "@/data/nearby-guide.json";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { cn } from "@/lib/utils";

type Destination = (typeof guide.destinations)[number];

export function NearbyDestinationExplorer() {
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState<string[]>([]);
  const visible = useMemo(() => filter === "All" ? guide.destinations : guide.destinations.filter((item) => item.tags.includes(filter)), [filter]);
  const selectedNames = guide.destinations.filter((item) => selected.includes(item.id)).map((item) => item.name);

  return (
    <>
      <div className="sticky top-[72px] z-30 -mx-4 border-y border-stone-200 bg-cream/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:rounded-2xl lg:border lg:bg-white lg:p-3">
        <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-wrap">
          {guide.filters.map((item) => <button key={item} onClick={() => setFilter(item)} className={`min-h-10 shrink-0 rounded-full px-4 text-sm font-bold transition ${filter === item ? "bg-maroon text-white" : "border border-stone-200 bg-white text-stone-600 hover:border-saffron"}`}>{item}</button>)}
        </div>
      </div>
      <p className="mt-6 text-sm text-stone-500">{visible.length} destination{visible.length === 1 ? "" : "s"} match “{filter}”.</p>
      <motion.div layout className="mt-6 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <AnimatePresence mode="popLayout">
          {visible.map((item) => <motion.div layout key={item.id} initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: .96 }} transition={{ duration: .25 }}><NearbyDestinationCard destination={item} selected={selected.includes(item.id)} onToggle={() => setSelected((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} /></motion.div>)}
        </AnimatePresence>
      </motion.div>
      <AnimatePresence>
        {selected.length > 0 && <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }} className="fixed inset-x-3 bottom-20 z-40 mx-auto max-w-3xl rounded-2xl border border-gold/50 bg-white p-4 shadow-2xl md:bottom-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div><p className="text-xs font-bold uppercase tracking-wider text-saffron">{selected.length} added to shortlist</p><p className="mt-1 text-sm font-bold text-ink">{selectedNames.join(", ")}</p></div>
            <div className="flex gap-2"><Button variant="ghost" size="sm" onClick={() => setSelected([])}><X className="h-4 w-4" />Clear</Button><Button asChild size="sm"><a href={`/plan-my-trip?add=${encodeURIComponent(selectedNames.join(","))}`}>Build itinerary <ArrowRight className="h-4 w-4" /></a></Button></div>
          </div>
        </motion.div>}
      </AnimatePresence>
    </>
  );
}

function NearbyDestinationCard({ destination, selected, onToggle }: { destination: Destination; selected: boolean; onToggle: () => void }) {
  return (
    <Card className={`group h-full overflow-hidden transition ${selected ? "border-saffron ring-2 ring-orange-100" : "border-stone-200"}`}>
      <div className={cn("relative h-44 overflow-hidden bg-gradient-to-br p-6 text-white", toneClass(destination.tone))}>
        <div className="pattern-arches absolute inset-0 opacity-25" />
        <div className="absolute -right-8 -top-8 h-28 w-28 rounded-full border border-white/15" />
        <div className="relative flex items-start justify-between"><span className="rounded-full border border-white/20 bg-black/10 px-3 py-1 text-[10px] font-bold uppercase tracking-widest">{destination.category}</span><MapPin className="h-6 w-6" /></div>
        <h3 className="relative mt-8 font-serif text-3xl text-white">{destination.name}</h3>
      </div>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 text-xs"><Meta label="Best base" value={destination.bestBase} /><Meta label="Ideal duration" value={destination.duration} /></div>
        <p className="mt-4 flex gap-2 rounded-xl bg-sand/60 p-3 text-xs leading-5 text-stone-600"><Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-saffron" />{destination.travelTime}</p>
        <h4 className="mt-5 text-sm font-bold">Why visit</h4><p className="mt-2 text-sm leading-6 text-stone-600">{destination.whyVisit}</p>
        <p className="mt-4 flex gap-2 text-xs leading-5 text-[#24664e]"><HeartHandshake className="mt-0.5 h-4 w-4 shrink-0" />{destination.suitability}</p>
        <div className="mt-4 flex flex-wrap gap-2">{destination.highlights.map((item) => <span key={item} className="rounded-full border border-stone-200 px-3 py-1 text-[10px] font-bold text-stone-600">{item}</span>)}</div>
        <div className="mt-6 grid grid-cols-3 gap-2">
          <Button asChild variant="outline" size="sm"><a href={`https://www.google.com/maps/dir/?api=1&origin=Ujjain&destination=${encodeURIComponent(destination.mapsQuery)}`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" /><span className="sr-only sm:not-sr-only">Map</span></a></Button>
          <Button onClick={onToggle} variant={selected ? "maroon" : "outline"} size="sm">{selected ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}<span className="sr-only sm:not-sr-only">{selected ? "Added" : "Add"}</span></Button>
          <Button asChild variant="whatsapp" size="sm"><a href={`https://wa.me/?text=${encodeURIComponent(`Add ${destination.name} to your Ujjain trip: https://ujjain2028.in/nearby-places`)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4" /><span className="sr-only">Share</span></a></Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div><span className="block text-[9px] font-bold uppercase tracking-wider text-stone-400">{label}</span><strong className="mt-1 block leading-5 text-ink">{value}</strong></div>;
}

function toneClass(tone: string) {
  if (tone === "maroon") return "from-maroon to-[#321013]";
  if (tone === "gold") return "from-[#a8742e] to-[#5b3515]";
  if (tone === "nature") return "from-[#38674b] to-[#183828]";
  if (tone === "blue") return "from-[#34546e] to-[#172d3c]";
  if (tone === "ink") return "from-ink to-stone-700";
  return "from-saffron to-[#963815]";
}

export function CircuitCards() {
  return <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">{guide.circuits.map((circuit, index) => <Card key={circuit.title} className="h-full overflow-hidden border-gold/35"><div className={`${index % 2 ? "bg-maroon" : "bg-saffron"} temple-silhouette p-5 text-white`}><Route className="h-6 w-6 text-gold" /><p className="mt-4 text-xs font-bold uppercase tracking-widest text-orange-100">{circuit.duration}</p><h3 className="mt-2 font-serif text-2xl text-white">{circuit.title}</h3></div><CardContent><p className="text-xs font-bold text-saffron">{circuit.bestFor}</p><ol className="relative mt-5 ml-3 border-l border-gold/50 pl-6">{circuit.stops.map((stop, stopIndex) => <li key={stop} className="relative pb-5 text-sm leading-6 text-stone-600 last:pb-0"><span className="absolute -left-[31px] top-1 grid h-4 w-4 place-items-center rounded-full bg-saffron text-[8px] font-bold text-white">{stopIndex + 1}</span>{stop}</li>)}</ol><Button asChild variant="outline" className="mt-6 w-full"><a href={`/plan-my-trip?add=${encodeURIComponent(circuit.title)}`}>Use this circuit</a></Button></CardContent></Card>)}</div>;
}

export function NearbyTravelTips() {
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{guide.tips.map((tip, index) => <Card key={tip.title} className="h-full bg-[#fffaf0] border-gold/35"><CardContent><span className="grid h-10 w-10 place-items-center rounded-xl bg-maroon text-gold"><Sparkles className="h-4 w-4" /></span><p className="mt-4 text-xs font-bold uppercase tracking-widest text-saffron">Tip 0{index + 1}</p><h3 className="mt-2 font-serif text-xl">{tip.title}</h3><p className="mt-3 text-sm leading-6 text-stone-600">{tip.description}</p></CardContent></Card>)}</div>;
}
