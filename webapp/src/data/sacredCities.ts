export type SacredCity = {
  slug: string;
  city: string;
  state: string;
  mainTemples: string[];
  spiritualImportance: string;
  bestTimeToVisit: string;
  suggestedDuration: string;
  nearestAirport: string;
  railwayStation: string;
  topItineraries: string[];
  packageCTA: string;
};

export const sacredCities: SacredCity[] = [
  { slug: "ujjain", city: "Ujjain", state: "Madhya Pradesh", mainTemples: ["Mahakaleshwar", "Kal Bhairav", "Harsiddhi Mata"], spiritualImportance: "Simhastha Kumbh city and home to Mahakaleshwar Jyotirlinga.", bestTimeToVisit: "October to March; Kumbh by official dates", suggestedDuration: "2–3 days", nearestAirport: "Indore", railwayStation: "Ujjain Junction", topItineraries: ["Ujjain 1 day", "Ujjain + Omkareshwar", "Indore base plan"], packageCTA: "Request Ujjain pilgrimage support" },
  { slug: "nashik", city: "Nashik", state: "Maharashtra", mainTemples: ["Trimbakeshwar", "Kalaram Temple", "Sita Gufa"], spiritualImportance: "Godavari pilgrimage city and Nashik-Trimbakeshwar Kumbh gateway.", bestTimeToVisit: "October to March", suggestedDuration: "2–3 days", nearestAirport: "Nashik / Mumbai", railwayStation: "Nashik Road", topItineraries: ["Nashik + Trimbakeshwar", "Nashik + Shirdi"], packageCTA: "Request Nashik Kumbh support" },
  { slug: "prayagraj", city: "Prayagraj", state: "Uttar Pradesh", mainTemples: ["Triveni Sangam", "Hanuman Mandir", "Akshayavat"], spiritualImportance: "Sangam city for Kumbh and Magh Mela pilgrimage.", bestTimeToVisit: "October to March; mela dates by official schedule", suggestedDuration: "2 days", nearestAirport: "Prayagraj", railwayStation: "Prayagraj Junction", topItineraries: ["Sangam snan", "Prayagraj + Varanasi", "Prayagraj + Ayodhya"], packageCTA: "Request Prayagraj pilgrimage support" },
  { slug: "haridwar", city: "Haridwar", state: "Uttarakhand", mainTemples: ["Har Ki Pauri", "Mansa Devi", "Chandi Devi"], spiritualImportance: "Ganga pilgrimage city and Char Dham gateway.", bestTimeToVisit: "October to March; Char Dham season for gateway travel", suggestedDuration: "1–2 days", nearestAirport: "Dehradun", railwayStation: "Haridwar Junction", topItineraries: ["Haridwar + Rishikesh", "Char Dham gateway"], packageCTA: "Request Haridwar travel support" },
  { slug: "varanasi", city: "Varanasi", state: "Uttar Pradesh", mainTemples: ["Kashi Vishwanath", "Annapurna Temple", "Sankat Mochan"], spiritualImportance: "Kashi is one of India’s most sacred cities and home to Kashi Vishwanath Jyotirlinga.", bestTimeToVisit: "October to March", suggestedDuration: "2–3 days", nearestAirport: "Varanasi", railwayStation: "Varanasi Junction", topItineraries: ["Kashi 2 days", "Varanasi + Prayagraj + Ayodhya"], packageCTA: "Request Kashi package" },
  { slug: "ayodhya", city: "Ayodhya", state: "Uttar Pradesh", mainTemples: ["Ram Mandir", "Hanuman Garhi", "Kanak Bhawan"], spiritualImportance: "Bhagwan Ram’s sacred city and major family pilgrimage destination.", bestTimeToVisit: "October to March", suggestedDuration: "1–2 days", nearestAirport: "Ayodhya / Lucknow", railwayStation: "Ayodhya Dham", topItineraries: ["Ayodhya 1 day", "Varanasi + Prayagraj + Ayodhya"], packageCTA: "Request Ayodhya package" },
  { slug: "mathura-vrindavan", city: "Mathura-Vrindavan", state: "Uttar Pradesh", mainTemples: ["Banke Bihari", "Krishna Janmabhoomi", "Prem Mandir"], spiritualImportance: "Krishna bhakti circuit for families and weekend temple trips.", bestTimeToVisit: "October to March", suggestedDuration: "2 days", nearestAirport: "Delhi / Agra", railwayStation: "Mathura Junction", topItineraries: ["Mathura + Vrindavan", "Barsana add-on"], packageCTA: "Request Braj package" },
  { slug: "shirdi", city: "Shirdi", state: "Maharashtra", mainTemples: ["Sai Baba Samadhi Mandir", "Dwarkamai", "Chavadi"], spiritualImportance: "Major Sai Baba pilgrimage destination, often combined with Nashik and Trimbakeshwar.", bestTimeToVisit: "October to March", suggestedDuration: "1 day", nearestAirport: "Shirdi / Nashik", railwayStation: "Sainagar Shirdi", topItineraries: ["Shirdi 1 day", "Nashik + Trimbakeshwar + Shirdi"], packageCTA: "Request Shirdi package" },
  { slug: "tirupati", city: "Tirupati", state: "Andhra Pradesh", mainTemples: ["Tirumala Venkateswara", "Padmavathi Temple"], spiritualImportance: "One of India’s busiest Vishnu pilgrimage destinations.", bestTimeToVisit: "September to February", suggestedDuration: "2 days", nearestAirport: "Tirupati", railwayStation: "Tirupati", topItineraries: ["Tirupati darshan", "Tirupati + Srikalahasti"], packageCTA: "Request Tirupati package" },
  { slug: "rameswaram", city: "Rameswaram", state: "Tamil Nadu", mainTemples: ["Ramanathaswamy Temple", "Dhanushkodi", "Panchmukhi Hanuman"], spiritualImportance: "Jyotirlinga and Char Dham-linked southern pilgrimage town.", bestTimeToVisit: "October to March", suggestedDuration: "2 days", nearestAirport: "Madurai", railwayStation: "Rameswaram", topItineraries: ["Madurai + Rameswaram", "Rameswaram + Kanyakumari"], packageCTA: "Request Rameswaram package" },
  { slug: "dwarka", city: "Dwarka", state: "Gujarat", mainTemples: ["Dwarkadhish", "Nageshwar", "Bet Dwarka"], spiritualImportance: "Krishna pilgrimage city and gateway to Nageshwar Jyotirlinga.", bestTimeToVisit: "October to March", suggestedDuration: "2 days", nearestAirport: "Jamnagar / Rajkot", railwayStation: "Dwarka", topItineraries: ["Dwarka + Nageshwar", "Somnath + Dwarka"], packageCTA: "Request Dwarka package" },
  { slug: "puri", city: "Puri", state: "Odisha", mainTemples: ["Jagannath Temple", "Gundicha Temple", "Konark nearby"], spiritualImportance: "Jagannath Dham and eastern India’s major pilgrimage centre.", bestTimeToVisit: "October to February", suggestedDuration: "2–3 days", nearestAirport: "Bhubaneswar", railwayStation: "Puri", topItineraries: ["Puri + Konark", "Bhubaneswar + Puri"], packageCTA: "Request Puri package" },
];

export function getSacredCity(slug: string) {
  return sacredCities.find((city) => city.slug === slug);
}
