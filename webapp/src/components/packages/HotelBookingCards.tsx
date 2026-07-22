import Link from "next/link";
import { ArrowRight, BedDouble, Building2, Landmark } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

const hotelOptions = [
  { city: "Ujjain", bestFor: "Walking access, early darshan, short trip", link: "/go/booking?city=ujjain&campaign=ujjain-kumbh-2028&sourcePage=legacy-hotel-cards", icon: Landmark },
  { city: "Indore", bestFor: "Better hotels, airport access, family comfort", link: "/go/booking?city=indore&campaign=ujjain-kumbh-2028&sourcePage=legacy-hotel-cards", icon: BedDouble },
  { city: "Bhopal", bestFor: "Extended MP trip, Omkareshwar/Sanchi add-on", link: "/go/booking?city=bhopal&campaign=ujjain-kumbh-2028&sourcePage=legacy-hotel-cards", icon: Building2 },
];

export function HotelBookingCards({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`grid gap-5 ${compact ? "md:grid-cols-3" : "lg:grid-cols-3"}`}>
      {hotelOptions.map(({ icon: Icon, ...option }) => (
        <Card key={option.city} className="h-full border-gold/35">
          <CardContent>
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-5 w-5" /></span>
            <h3 className="mt-5 font-serif text-2xl">Stay in {option.city}</h3>
            <p className="mt-3 text-sm leading-6 text-stone-600"><strong>Best for:</strong> {option.bestFor}</p>
            <Link href={option.link} target="_blank" rel="noopener noreferrer" className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">
              Check {option.city} Hotels<ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
