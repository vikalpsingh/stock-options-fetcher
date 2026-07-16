import Link from "next/link";
import { ArrowRight, BedDouble, BusFront, Plane, TrainFront } from "lucide-react";
import { getTravelCityBySlug } from "@/src/data/travelCities";
import { getRecommendedRoutes } from "@/src/data/kumbhTravelRoutes";
import { addDays } from "@/src/lib/travel/validation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function RecommendedRouteCards({
  destinationSlug = "ujjain-kumbh-2028",
  sourcePage = "recommended-routes",
}: {
  destinationSlug?: string;
  sourcePage?: string;
}) {
  const routes = getRecommendedRoutes(destinationSlug);
  const date = addDays(new Date().toISOString().slice(0, 10), 30);
  const checkout = addDays(date, 2);
  return (
    <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
      {routes.map((route) => {
        const source = getTravelCityBySlug(route.sourceCitySlug)!;
        const stay = getTravelCityBySlug(route.recommendedStayCitySlug)!;
        const busTo = getTravelCityBySlug(route.busDestinationSlug)!;
        const flightTo = getTravelCityBySlug(route.flightDestinationSlug)!;
        const trainTo = getTravelCityBySlug(route.trainDestinationSlug)!;
        const common = `campaign=ujjain-kumbh-2028&sourcePage=${sourcePage}`;
        return (
          <Card key={route.id} className="h-full border-gold/35 bg-[#fffdf8]">
            <CardContent>
              <p className="text-xs font-black uppercase tracking-[.18em] text-saffron">{source.cityName} to Ujjain</p>
              <h3 className="mt-3 font-serif text-2xl">{route.bestFor}</h3>
              <p className="mt-3 text-sm leading-7 text-stone-600">{route.advice}</p>
              <p className="mt-4 rounded-2xl bg-orange-50 p-3 text-xs leading-5 text-maroon"><strong>Recommended stay:</strong> {stay.cityName}</p>
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                <Button asChild variant="outline" size="sm"><Link href={`/go/travel?mode=bus&from=${source.slug}&to=${busTo.slug}&date=${date}&${common}`}><BusFront className="h-4 w-4" />Bus</Link></Button>
                <Button asChild variant="outline" size="sm"><Link href={`/go/travel?mode=flight&from=${source.slug}&to=${flightTo.slug}&departureDate=${date}&adults=2&${common}`}><Plane className="h-4 w-4" />Flight</Link></Button>
                <Button asChild variant="outline" size="sm"><Link href={`/go/travel?mode=train&from=${source.slug}&to=${trainTo.slug}&date=${date}&${common}`}><TrainFront className="h-4 w-4" />Train</Link></Button>
                <Button asChild size="sm"><Link href={`/go/travel?mode=hotel&city=${stay.slug}&checkin=${date}&checkout=${checkout}&adults=2&rooms=1&${common}`}><BedDouble className="h-4 w-4" />Hotel</Link></Button>
              </div>
              <p className="mt-4 text-[11px] leading-5 text-stone-500">Booking is completed on partner website. IndianKumbh.com may earn a referral commission.</p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
