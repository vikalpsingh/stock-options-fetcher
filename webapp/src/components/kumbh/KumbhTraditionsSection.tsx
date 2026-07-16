import { Flag, Flame, Landmark, MessageCircle, Waves } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { KumbhGuide } from "@/src/data/kumbhGuides";

const traditions = [
  { title: "Akharas", icon: Landmark, text: "Akharas are traditional religious institutions. Akharas and sadhu traditions are central to Kumbh processions, camps and bathing rituals." },
  { title: "Naga Sadhus", icon: Flame, text: "Naga sadhus are ascetic monks associated with renunciation and akhara traditions. Their processions are one of the most recognised sights of Kumbh." },
  { title: "Shahi Snan / Amrit Snan", icon: Waves, text: "These are the most auspicious bathing days when akharas and pilgrims gather at sacred river ghats." },
  { title: "Dhwajarohan", icon: Flag, text: "Flag-hoisting ceremonies mark the formal beginning of the Kumbh period in traditional observance." },
  { title: "Pravachan and satsang", icon: MessageCircle, text: "Religious discourses, bhajan, katha and spiritual camps are important for pilgrims beyond the holy bath." },
];

export function KumbhTraditionsSection({ guide }: { guide: KumbhGuide }) {
  const specific = guide.slug.includes("nashik")
    ? ["Ramkund", "Kushavarta Kund", "Trimbakeshwar", "Godavari", "Panchavati"]
    : ["Ram Ghat", "Shipra", "Mahakaleshwar", "Akhara processions", "Simhastha camps"];
  return (
    <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-7xl">
        <p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Traditions</p>
        <h2 className="mt-3 font-serif text-4xl font-semibold">Famous names, akharas and Kumbh traditions</h2>
        <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {traditions.map(({ icon: Icon, ...item }) => <Card key={item.title} className="border-gold/35"><CardContent><Icon className="h-6 w-6 text-saffron" /><h3 className="mt-4 font-serif text-2xl">{item.title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{item.text}</p></CardContent></Card>)}
        </div>
        <Card className="mt-6 border-gold/35 bg-sand"><CardContent><h3 className="font-serif text-2xl">Destination-specific traditions for {guide.shortTitle}</h3><div className="mt-4 flex flex-wrap gap-2">{specific.map((item) => <span key={item} className="rounded-full bg-white px-3 py-2 text-sm font-bold text-maroon">{item}</span>)}</div><p className="mt-5 text-xs leading-5 text-stone-500">Names of participating akharas, saints and camps should be updated from official announcements closer to the event.</p></CardContent></Card>
      </div>
    </section>
  );
}
