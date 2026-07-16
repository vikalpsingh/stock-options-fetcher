export type KumbhTravelRoute = {
  id: string;
  destinationSlug: string;
  sourceCitySlug: string;
  recommendedStayCitySlug: string;
  busDestinationSlug: string;
  flightDestinationSlug: string;
  trainDestinationSlug: string;
  bestFor: string;
  advice: string;
  priority: number;
};

export const kumbhTravelRoutes: KumbhTravelRoute[] = [
  { id: "blr-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "bengaluru", recommendedStayCitySlug: "indore", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Families flying from South India", advice: "Fly to Indore for family comfort; stay in Indore if Ujjain hotels are full.", priority: 1 },
  { id: "mumbai-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "mumbai", recommendedStayCitySlug: "ujjain", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Direct train-first travellers", advice: "Try trains to Ujjain first; use Indore as a hotel and airport fallback.", priority: 2 },
  { id: "pune-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "pune", recommendedStayCitySlug: "indore", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Bus/train comparisons", advice: "Compare bus and train availability to Ujjain; fly to Indore when travelling with parents or kids.", priority: 3 },
  { id: "delhi-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "delhi", recommendedStayCitySlug: "indore", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Long-distance family travel", advice: "Flight to Indore plus a buffered road transfer is usually easier for families than aggressive train timing.", priority: 4 },
  { id: "ahmedabad-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "ahmedabad", recommendedStayCitySlug: "ujjain", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Western India road/train travellers", advice: "Bus and train to Ujjain are practical; book stay early for bathing days.", priority: 5 },
  { id: "hyderabad-ujjain-2028", destinationSlug: "ujjain-kumbh-2028", sourceCitySlug: "hyderabad", recommendedStayCitySlug: "indore", busDestinationSlug: "ujjain", flightDestinationSlug: "indore", trainDestinationSlug: "ujjain", bestFor: "Flight-first travellers", advice: "Fly to Indore and keep Ujjain darshan as a separate, early-start day.", priority: 6 },
];

export function getRecommendedRoutes(destinationSlug: string) {
  return kumbhTravelRoutes.filter((route) => route.destinationSlug === destinationSlug).sort((a, b) => a.priority - b.priority);
}
