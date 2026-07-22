import Link from "next/link";
import { ArrowRight, BedDouble, Building2, Landmark, ShieldCheck } from "lucide-react";
import { getDefaultHotelDates } from "@/src/lib/buildBookingUrl";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type HotelBookingCTAProps = {
  title?: string;
  sourcePage: string;
  campaign?: string;
  checkin?: string;
  checkout?: string;
};

const ujjainHotelCards = [
  {
    city: "ujjain",
    title: "Ujjain Hotels",
    bestFor: "Mahakal darshan, early snan, short pilgrimage stay",
    cta: "Check Ujjain Hotels",
    icon: Landmark,
  },
  {
    city: "indore",
    title: "Indore Hotels",
    bestFor: "Airport access, better hotel choice, family comfort",
    cta: "Check Indore Hotels",
    icon: Building2,
    featured: true,
  },
  {
    city: "bhopal",
    title: "Bhopal Hotels",
    bestFor: "Extended MP trip and family itinerary",
    cta: "Check Bhopal Hotels",
    icon: BedDouble,
  },
];

const nashikHotelCards = [
  {
    city: "nashik",
    title: "Nashik Hotels",
    bestFor: "Ramkund, Godavari snan, family stay and city access",
    cta: "Check Nashik Hotels",
    icon: Landmark,
    featured: true,
  },
  {
    city: "pune",
    title: "Pune Hotels",
    bestFor: "Flight/road access, family comfort and arrival buffer",
    cta: "Check Pune Hotels",
    icon: Building2,
  },
  {
    city: "mumbai",
    title: "Mumbai Hotels",
    bestFor: "International airport access, premium hotels and departure buffer",
    cta: "Check Mumbai Hotels",
    icon: BedDouble,
  },
];

export function HotelBookingCTA({
  title = "Book Stay for Ujjain Kumbh 2028",
  sourcePage,
  campaign = "ujjain-kumbh-2028",
  checkin,
  checkout,
}: HotelBookingCTAProps) {
  const isNashik = campaign.includes("nashik") || sourcePage.includes("nashik") || title.toLowerCase().includes("nashik");
  const cards = isNashik ? nashikHotelCards : ujjainHotelCards;
  const intro = isNashik
    ? "Stay in Nashik for Ramkund and city access, or use Pune/Mumbai as practical arrival and departure hotel hubs for family travellers."
    : "Stay in Indore, visit Ujjain for Kumbh Snan and Mahakal Darshan, or choose Ujjain for a shorter high-intent pilgrimage stay.";
  return (
    <div className="rounded-[2rem] border border-gold/30 bg-[#fffdf8] p-5 shadow-soft sm:p-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Hotel booking partner</p>
          <h2 className="mt-2 font-serif text-3xl font-semibold text-ink sm:text-4xl">{title}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-stone-600">{intro}</p>
        </div>
        <p className="rounded-full bg-amber-50 px-4 py-2 text-xs font-bold text-amber-900">Sponsored / affiliate link</p>
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {cards.map(({ icon: Icon, ...card }) => {
          const dates = checkin && checkout ? { checkin, checkout } : getDefaultHotelDates(card.city);
          const href = `/go/booking?${new URLSearchParams({
            city: card.city,
            checkin: dates.checkin,
            checkout: dates.checkout,
            adults: "2",
            rooms: "1",
            children: "0",
            budget: "standard",
            campaign,
            sourcePage,
          }).toString()}`;
          return (
            <Card key={card.city} className={`h-full border-gold/35 ${card.featured ? "bg-orange-50 ring-2 ring-orange-100" : "bg-white"}`}>
              <CardContent>
                <span className={`grid h-12 w-12 place-items-center rounded-2xl ${card.featured ? "bg-saffron text-white" : "bg-sand text-maroon"}`}><Icon className="h-6 w-6" /></span>
                <h3 className="mt-5 font-serif text-2xl">{card.title}</h3>
                <p className="mt-3 text-sm leading-7 text-stone-600"><strong>Best for:</strong> {card.bestFor}</p>
                <Button asChild className="mt-6 w-full" variant={card.featured ? "default" : "outline"}>
                  <Link href={href} target="_blank" rel="noopener noreferrer">{card.cta}<ArrowRight className="h-4 w-4" /></Link>
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <p className="mt-6 flex gap-2 rounded-2xl bg-white p-4 text-xs leading-5 text-stone-600"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-saffron" />Booking is completed on Booking.com. Availability, price, cancellation and refund terms are handled by Booking.com or the hotel.</p>
    </div>
  );
}
