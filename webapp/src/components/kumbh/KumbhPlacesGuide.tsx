"use client";

import { useState } from "react";
import { MapPin, Plus, Route } from "lucide-react";
import type { KumbhGuide } from "@/src/data/kumbhGuides";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const filters = [
  { label: "Must visit", tag: "must_visit" },
  { label: "Senior friendly", tag: "senior_friendly" },
  { label: "Near main Kumbh area", tag: "near_main_kumbh_area" },
  { label: "Jyotirlinga", tag: "jyotirlinga" },
  { label: "Nearby add-on", tag: "nearby_add_on" },
  { label: "Family friendly", tag: "family_friendly" },
];

export function KumbhPlacesGuide({ guide }: { guide: KumbhGuide }) {
  const [active, setActive] = useState("");
  const places = active ? guide.keyPlaces.filter((place) => place.tags.includes(active)) : guide.keyPlaces;
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setActive("")} className={`rounded-full border px-4 py-2 text-sm font-bold ${!active ? "border-saffron bg-orange-50 text-maroon" : "border-stone-200 bg-white"}`}>All</button>
        {filters.map((filter) => <button key={filter.tag} onClick={() => setActive(filter.tag)} className={`rounded-full border px-4 py-2 text-sm font-bold ${active === filter.tag ? "border-saffron bg-orange-50 text-maroon" : "border-stone-200 bg-white"}`}>{filter.label}</button>)}
      </div>
      <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {places.map((place) => <Card key={place.name} className="h-full border-gold/35 bg-[#fffdf8]"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{place.type.replaceAll("_", " ")}</p><h3 className="mt-3 font-serif text-2xl">{place.name}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{place.importance}</p><div className="mt-4 space-y-2 text-xs leading-5 text-stone-600"><p><strong>Tip:</strong> {place.travellerTip}</p><p><strong>Best time:</strong> {place.bestTimeToVisit}</p><p><strong>Senior suitability:</strong> {place.seniorCitizenSuitability}</p><p><strong>Suggested duration:</strong> {place.suggestedDuration}</p><p><strong>Nearby:</strong> {place.nearbyPlaces.join(", ")}</p></div><Button variant="outline" className="mt-5 w-full"><Plus className="h-4 w-4" />Add to itinerary</Button></CardContent></Card>)}
      </div>
      <div className="mt-8 rounded-[2rem] border border-dashed border-gold/50 bg-sand p-8 text-center">
        <MapPin className="mx-auto h-10 w-10 text-saffron" />
        <h3 className="mt-4 font-serif text-2xl">Map placeholder</h3>
        <p className="mt-2 text-sm leading-7 text-stone-600">Future integration can show official zones, ghats, temple areas, parking and verified walking routes.</p>
        <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-xs font-bold text-maroon"><Route className="h-4 w-4" />Use official maps when published</p>
      </div>
    </div>
  );
}
