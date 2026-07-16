export type PilgrimagePillar = {
  slug: string;
  title: string;
  shortDescription: string;
  priority: number;
  type: "kumbh" | "char_dham" | "jyotirlinga" | "temple_circuit" | "sacred_city" | "senior_citizen";
  primaryCTA: string;
  secondaryCTA: string;
  imageAlt: string;
};

export const pilgrimagePillars: PilgrimagePillar[] = [
  { slug: "kumbh-mela", title: "Kumbh Mela Guides", shortDescription: "Nashik 2027, Ujjain 2028, Prayagraj and Haridwar planning with stay, routes, crowd and senior citizen guidance.", priority: 1, type: "kumbh", primaryCTA: "Explore Kumbh Mela", secondaryCTA: "View calendar", imageAlt: "Pilgrims at a sacred river during Kumbh Mela" },
  { slug: "char-dham-yatra", title: "Char Dham Yatra", shortDescription: "Registration, route map, health notes, senior citizen planning and package guidance for Yamunotri, Gangotri, Kedarnath and Badrinath.", priority: 2, type: "char_dham", primaryCTA: "Plan Char Dham", secondaryCTA: "Registration guide", imageAlt: "Himalayan Char Dham temple route" },
  { slug: "12-jyotirlinga", title: "12 Jyotirlinga Darshan", shortDescription: "Practical temple-by-temple guide for all Jyotirlingas, including Mahakaleshwar, Omkareshwar, Trimbakeshwar and Kashi Vishwanath.", priority: 3, type: "jyotirlinga", primaryCTA: "View Jyotirlingas", secondaryCTA: "Complete itinerary", imageAlt: "Jyotirlinga temple circuit map in India" },
  { slug: "temple-circuits", title: "Temple Circuits", shortDescription: "Ready route ideas such as Ujjain–Omkareshwar–Maheshwar, Nashik–Trimbakeshwar–Shirdi and Varanasi–Prayagraj–Ayodhya.", priority: 4, type: "temple_circuit", primaryCTA: "Explore circuits", secondaryCTA: "Request package", imageAlt: "Indian temple circuit road journey" },
  { slug: "sacred-cities", title: "Sacred City Guides", shortDescription: "City travel guides for Ujjain, Nashik, Varanasi, Ayodhya, Haridwar, Prayagraj, Shirdi, Rameswaram, Dwarka and Puri.", priority: 5, type: "sacred_city", primaryCTA: "View cities", secondaryCTA: "Search hotels", imageAlt: "Sacred Indian city with temple ghats" },
  { slug: "senior-citizen-yatra", title: "Senior Citizen Yatra", shortDescription: "Slower itineraries, stay decisions, medical buffers, transport choices and assisted pilgrimage planning for parents and elders.", priority: 6, type: "senior_citizen", primaryCTA: "Plan senior yatra", secondaryCTA: "Get package help", imageAlt: "Family helping senior pilgrims at a temple" },
];
