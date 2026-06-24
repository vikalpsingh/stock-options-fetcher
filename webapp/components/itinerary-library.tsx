"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Accessibility,
  ArrowRight,
  BedDouble,
  Check,
  ChevronDown,
  Clock3,
  Gauge,
  HeartHandshake,
  MapPin,
  MessageCircle,
  Navigation,
  Printer,
  Route,
  Save,
  Soup,
  Sparkles,
  SunMedium,
  Users,
} from "lucide-react";
import itineraries from "@/data/itinerary-guide.json";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

type Itinerary = (typeof itineraries)[number];

export function ItineraryLibrary() {
  const [openId, setOpenId] = useState<string>(itineraries[0].id);
  return (
    <div className="space-y-7">
      {itineraries.map((itinerary, index) => {
        const open = openId === itinerary.id;
        return <ItineraryEntry key={itinerary.id} itinerary={itinerary} index={index} open={open} onToggle={() => setOpenId(open ? "" : itinerary.id)} />;
      })}
    </div>
  );
}

function ItineraryEntry({ itinerary, index, open, onToggle }: { itinerary: Itinerary; index: number; open: boolean; onToggle: () => void }) {
  const shareText = `${itinerary.title}: ${itinerary.highlights.join(", ")}. View the plan: https://ujjain2028.in/itineraries#${itinerary.id}`;
  return (
    <article id={itinerary.id} className="scroll-mt-28 overflow-hidden rounded-[2rem] border border-gold/40 bg-white shadow-soft">
      <div className="grid lg:grid-cols-[.42fr_.58fr]">
        <div className={`${index % 2 ? "bg-maroon" : "bg-saffron"} temple-silhouette p-6 text-white sm:p-8`}>
          <div className="flex items-center justify-between"><span className="rounded-full border border-white/20 bg-black/10 px-3 py-1 text-xs font-bold">{itinerary.days} {itinerary.days === 1 ? "Day" : "Days"}</span><Route className="h-6 w-6 text-gold" /></div>
          <h2 className="mt-6 font-serif text-3xl text-white sm:text-4xl">{itinerary.title}</h2>
          <p className="mt-3 text-sm leading-6 text-orange-50/75">{itinerary.bestFor}</p>
          <div className="mt-6 flex flex-wrap gap-2">{itinerary.highlights.map((item) => <span key={item} className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[10px] font-bold">{item}</span>)}</div>
        </div>
        <div className="p-6 sm:p-8">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Meta icon={MapPin} label="Start city" value={itinerary.startCity} />
            <Meta icon={BedDouble} label="Suggested base" value={itinerary.base} />
            <Meta icon={Gauge} label="Difficulty" value={itinerary.difficulty} />
            <Meta icon={Accessibility} label="Elderly rating" value={itinerary.elderlyRating} />
          </div>
          <p className="mt-5 flex gap-2 rounded-xl bg-sand/60 p-4 text-sm leading-6 text-stone-600"><Route className="mt-0.5 h-5 w-5 shrink-0 text-saffron" /><span><strong className="text-ink">Travel style:</strong> {itinerary.travelStyle}</span></p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button onClick={onToggle} variant={open ? "maroon" : "default"}>{open ? "Hide detailed plan" : "View detailed plan"}<ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} /></Button>
            <Button asChild variant="whatsapp"><a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4" />Share</a></Button>
          </div>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {open && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: .35 }} className="overflow-hidden">
          <div className="border-t border-stone-200 bg-cream p-5 sm:p-8">
            <div className="space-y-6">{itinerary.daysPlan.map((day) => <DayTimeline key={day.day} day={day} />)}</div>
            <div className="print-hidden mt-8 flex flex-wrap gap-3 border-t border-stone-200 pt-7">
              <Button onClick={() => window.print()} variant="outline"><Printer className="h-4 w-4" />Print itinerary</Button>
              <Button variant="outline" title="Use Print and select Save as PDF"><Save className="h-4 w-4" />Save as PDF</Button>
              <Button asChild variant="whatsapp"><a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4" />Share on WhatsApp</a></Button>
              <Button asChild><a href={`/plan-my-trip?template=${encodeURIComponent(itinerary.title)}`}>Customize this itinerary <ArrowRight className="h-4 w-4" /></a></Button>
            </div>
          </div>
        </motion.div>}
      </AnimatePresence>
    </article>
  );
}

function Meta({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return <div><Icon className="h-5 w-5 text-saffron" /><span className="mt-2 block text-[10px] font-bold uppercase tracking-wider text-stone-400">{label}</span><strong className="mt-1 block text-xs leading-5 text-ink">{value}</strong></div>;
}

function DayTimeline({ day }: { day: Itinerary["daysPlan"][number] }) {
  return (
    <Card className="overflow-hidden border-gold/30">
      <div className="flex items-center gap-4 border-b border-stone-200 bg-white px-5 py-4 sm:px-6"><span className="grid h-10 w-10 place-items-center rounded-full bg-maroon font-bold text-white">D{day.day}</span><div><p className="text-xs font-bold uppercase tracking-widest text-saffron">Day {day.day}</p><h3 className="font-serif text-xl">{day.title}</h3></div></div>
      <CardContent>
        <div className="grid gap-4 lg:grid-cols-3">
          <TimeBlock icon={SunMedium} label="Morning" text={day.morning} />
          <TimeBlock icon={Clock3} label="Afternoon" text={day.afternoon} />
          <TimeBlock icon={Sparkles} label="Evening" text={day.evening} />
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Detail icon={Soup} label="Food" text={day.food} />
          <Detail icon={BedDouble} label="Stay" text={day.stay} />
          <Detail icon={Clock3} label="Travel buffer" text={day.buffer} />
          <Detail icon={HeartHandshake} label="Family tip" text={day.familyTip} />
        </div>
        <div className="print-hidden mt-5 flex flex-wrap gap-2">{day.maps.map((place) => <Button key={place} asChild variant="outline" size="sm"><a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place)}`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" />{place}</a></Button>)}</div>
      </CardContent>
    </Card>
  );
}

function TimeBlock({ icon: Icon, label, text }: { icon: React.ComponentType<{ className?: string }>; label: string; text: string }) {
  return <div className="rounded-2xl bg-sand/65 p-4"><Icon className="h-5 w-5 text-saffron" /><p className="mt-3 text-xs font-extrabold uppercase tracking-wider text-maroon">{label}</p><p className="mt-2 text-sm leading-6 text-stone-600">{text}</p></div>;
}

function Detail({ icon: Icon, label, text }: { icon: React.ComponentType<{ className?: string }>; label: string; text: string }) {
  return <div className="flex gap-3"><Icon className="mt-0.5 h-5 w-5 shrink-0 text-gold" /><div><p className="text-xs font-bold text-ink">{label}</p><p className="mt-1 text-xs leading-5 text-stone-600">{text}</p></div></div>;
}
