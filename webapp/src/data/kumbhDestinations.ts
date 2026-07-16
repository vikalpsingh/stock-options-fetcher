export type KumbhDestination = {
  slug: string;
  title: string;
  primaryCitySlug: string;
  recommendedHotelCitySlugs: string[];
  defaultBusDestinationSlug: string;
  defaultFlightDestinationSlug: string;
  defaultTrainDestinationSlug: string;
  packageDestinationSlug: string;
  priority: number;
};

export const kumbhDestinations: KumbhDestination[] = [
  { slug: "ujjain-kumbh-2028", title: "Ujjain Simhastha Kumbh 2028", primaryCitySlug: "ujjain", recommendedHotelCitySlugs: ["indore", "ujjain", "bhopal"], defaultBusDestinationSlug: "ujjain", defaultFlightDestinationSlug: "indore", defaultTrainDestinationSlug: "ujjain", packageDestinationSlug: "ujjain-kumbh-2028", priority: 1 },
  { slug: "nashik-kumbh-2027", title: "Nashik-Trimbakeshwar Kumbh 2027", primaryCitySlug: "nashik", recommendedHotelCitySlugs: ["nashik", "mumbai"], defaultBusDestinationSlug: "nashik", defaultFlightDestinationSlug: "nashik", defaultTrainDestinationSlug: "nashik", packageDestinationSlug: "nashik-kumbh-2027", priority: 2 },
  { slug: "prayagraj-kumbh", title: "Prayagraj Kumbh Guide", primaryCitySlug: "prayagraj", recommendedHotelCitySlugs: ["prayagraj", "varanasi"], defaultBusDestinationSlug: "prayagraj", defaultFlightDestinationSlug: "prayagraj", defaultTrainDestinationSlug: "prayagraj", packageDestinationSlug: "prayagraj-kumbh", priority: 3 },
  { slug: "haridwar-kumbh", title: "Haridwar Kumbh Guide", primaryCitySlug: "haridwar", recommendedHotelCitySlugs: ["haridwar", "delhi"], defaultBusDestinationSlug: "haridwar", defaultFlightDestinationSlug: "haridwar", defaultTrainDestinationSlug: "haridwar", packageDestinationSlug: "haridwar-kumbh", priority: 4 },
];
