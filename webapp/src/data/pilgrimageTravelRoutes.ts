export type PilgrimageTravelRoute = {
  id: string;
  pillar: "char-dham" | "jyotirlinga";
  title: string;
  startCity: string;
  endCity: string;
  advice: string;
  href: string;
};

export const pilgrimageTravelRoutes: PilgrimageTravelRoute[] = [
  { id: "delhi-char-dham", pillar: "char-dham", title: "Delhi / Haridwar to Char Dham", startCity: "Delhi / Haridwar", endCity: "Yamunotri → Gangotri → Kedarnath → Badrinath", advice: "Keep 10-14 days for balanced road travel with weather buffer.", href: "/char-dham-yatra/route-map" },
  { id: "do-dham", pillar: "char-dham", title: "Kedarnath + Badrinath Do Dham", startCity: "Haridwar / Rishikesh", endCity: "Kedarnath and Badrinath", advice: "Useful for travellers with fewer days; still keep altitude and weather buffer.", href: "/char-dham-yatra/packages" },
  { id: "mp-jyotirlinga", pillar: "jyotirlinga", title: "MP Jyotirlinga Circuit", startCity: "Indore / Ujjain", endCity: "Mahakaleshwar + Omkareshwar", advice: "Good 2-3 day circuit for families and senior citizens.", href: "/12-jyotirlinga/complete-itinerary" },
  { id: "maharashtra-jyotirlinga", pillar: "jyotirlinga", title: "Maharashtra Jyotirlinga Circuit", startCity: "Nashik / Pune / Chhatrapati Sambhajinagar", endCity: "Trimbakeshwar + Bhimashankar + Grishneshwar", advice: "Plan as separate legs if travelling with elders.", href: "/12-jyotirlinga/complete-itinerary" },
  { id: "gujarat-jyotirlinga", pillar: "jyotirlinga", title: "Gujarat Shiva Circuit", startCity: "Rajkot / Ahmedabad", endCity: "Somnath + Nageshwar + Dwarka", advice: "Senior-friendly when paced over 3-5 days.", href: "/12-jyotirlinga/complete-itinerary" },
];
