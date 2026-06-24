"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Baby,
  Check,
  Clock3,
  Droplets,
  HeartHandshake,
  MapPin,
  MoonStar,
  ShieldCheck,
  Soup,
  Sparkles,
  SunMedium,
  Utensils,
  Zap,
} from "lucide-react";
import guide from "@/data/food-guide.json";
import { Card, CardContent } from "./ui/card";

type Food = (typeof guide.foods)[number];

export function CityFoodExplorer() {
  const [city, setCity] = useState("Ujjain");
  const foods = useMemo(() => guide.foods.filter((food) => food.cities.includes(city)), [city]);
  return (
    <>
      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-stone-200 bg-white p-2">
        {guide.cities.map((item) => <button key={item} onClick={() => setCity(item)} className={`min-h-11 flex-1 shrink-0 rounded-xl px-5 text-sm font-bold transition ${city === item ? "bg-maroon text-white" : "text-stone-600 hover:bg-sand"}`}>{item}</button>)}
      </div>
      <p className="mt-5 text-sm text-stone-500">{foods.length} recommended foods commonly associated with {city} or the wider region.</p>
      <motion.div layout className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <AnimatePresence mode="popLayout">
          {foods.map((food, index) => <motion.div layout key={food.id} initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: .96 }} transition={{ duration: .24, delay: index * .025 }}><DetailedFoodCard food={food} city={city} /></motion.div>)}
        </AnimatePresence>
      </motion.div>
    </>
  );
}

function DetailedFoodCard({ food, city }: { food: Food; city: string }) {
  const gradient = ["from-orange-500 to-rose-800", "from-amber-500 to-orange-800", "from-[#8f4a35] to-maroon", "from-[#b28a31] to-[#674216]"][food.name.length % 4];
  return (
    <Card className="h-full overflow-hidden border-gold/30">
      <div className={`relative h-36 bg-gradient-to-br ${gradient} p-5 text-white`}>
        <div className="pattern-mandala absolute inset-0 opacity-20" />
        <Utensils className="relative h-7 w-7 text-gold" />
        <h3 className="relative mt-5 font-serif text-2xl text-white">{food.name}</h3>
      </div>
      <CardContent>
        <div className="flex flex-wrap gap-2"><Badge>{city}</Badge><Badge>Vegetarian</Badge>{food.familyFriendly && <Badge green>Family-friendly</Badge>}</div>
        <div className="mt-5 grid grid-cols-2 gap-3 text-xs"><Meta label="Best time" value={food.bestTime} /><Meta label="Meal feel" value={food.weight} /></div>
        <p className="mt-4 text-sm leading-6 text-stone-600">{food.description}</p>
        {!food.familyFriendly && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-900">Confirm all ingredients before ordering for children or family members.</p>}
      </CardContent>
    </Card>
  );
}

function Badge({ children, green = false }: { children: React.ReactNode; green?: boolean }) {
  return <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${green ? "bg-[#eaf7f0] text-[#24664e]" : "bg-sand text-stone-600"}`}>{children}</span>;
}
function Meta({ label, value }: { label: string; value: string }) {
  return <div><span className="block text-[9px] font-bold uppercase tracking-wider text-stone-400">{label}</span><strong className="mt-1 block leading-5 text-ink">{value}</strong></div>;
}

export function IndoreFoodHighlights() {
  const icons = [MoonStar, MapPin, Utensils, Clock3];
  return <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">{guide.indoreHighlights.map((item, index) => { const Icon = icons[index]; return <Card key={item.title} className="h-full overflow-hidden"><div className="brand-gradient pattern-mandala p-6 text-white"><Icon className="h-7 w-7 text-gold" /><p className="mt-5 text-xs font-bold uppercase tracking-widest text-orange-100">{item.bestTime}</p><h3 className="mt-2 font-serif text-2xl text-white">{item.title}</h3><p className="mt-1 text-xs text-gold">{item.subtitle}</p></div><CardContent><p className="text-sm leading-6 text-stone-600">{item.description}</p><ul className="mt-5 space-y-2">{item.notes.map((note) => <li key={note} className="flex gap-2 text-xs text-stone-600"><Check className="h-3.5 w-3.5 shrink-0 text-saffron" />{note}</li>)}</ul></CardContent></Card>; })}</div>;
}

export function FoodSafetyTips() {
  const icons = [Droplets, Soup, Zap, Baby, ShieldCheck];
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{guide.safetyTips.map((tip, index) => { const Icon = icons[index]; return <Card key={tip.title} className="h-full border-gold/35 bg-[#fffaf0]"><CardContent><span className="grid h-10 w-10 place-items-center rounded-xl bg-maroon text-gold"><Icon className="h-5 w-5" /></span><h3 className="mt-4 font-bold">{tip.title}</h3><p className="mt-2 text-sm leading-6 text-stone-600">{tip.description}</p></CardContent></Card>; })}</div>;
}

export function FoodItineraryTimeline() {
  const icons = [SunMedium, Sparkles, MoonStar];
  return (
    <Card className="overflow-hidden border-gold/40">
      <div className="brand-gradient pattern-mandala p-7 text-white sm:p-9"><p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Suggested food itinerary</p><h3 className="mt-2 font-serif text-3xl text-white">Eat well without disrupting darshan</h3></div>
      <CardContent>
        <ol className="relative ml-4 border-l border-gold/50 pl-8">
          {guide.foodItinerary.map((item, index) => { const Icon = icons[index]; return <li key={item.title} className="relative pb-8 last:pb-0"><span className="absolute -left-[44px] grid h-8 w-8 place-items-center rounded-full bg-saffron text-white ring-4 ring-orange-50"><Icon className="h-4 w-4" /></span><div className="flex flex-wrap items-baseline justify-between gap-2"><h4 className="font-serif text-xl">{item.title}</h4><span className="text-xs font-bold text-saffron">{item.time}</span></div><p className="mt-2 text-sm leading-6 text-stone-700">{item.plan}</p><p className="mt-3 flex gap-2 text-xs leading-5 text-[#24664e]"><HeartHandshake className="h-4 w-4 shrink-0" />{item.tip}</p></li>; })}
        </ol>
      </CardContent>
    </Card>
  );
}
