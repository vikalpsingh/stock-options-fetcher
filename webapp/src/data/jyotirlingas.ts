export type Jyotirlinga = {
  slug: string;
  templeName: string;
  deityName: string;
  city: string;
  state: string;
  nearestAirport: string;
  nearestRailwayStation: string;
  bestTimeToVisit: string;
  suggestedDuration: string;
  nearbyPlaces: string[];
  circuitSlug: string;
  seniorCitizenDifficulty: "easy" | "moderate" | "difficult";
  shortDescription: string;
};

export const jyotirlingas: Jyotirlinga[] = [
  { slug: "somnath", templeName: "Somnath Jyotirlinga", deityName: "Somnath Mahadev", city: "Somnath", state: "Gujarat", nearestAirport: "Diu / Rajkot", nearestRailwayStation: "Veraval", bestTimeToVisit: "October to March", suggestedDuration: "1–2 days", nearbyPlaces: ["Prabhas Patan", "Diu", "Gir"], circuitSlug: "somnath-dwarka-nageshwar", seniorCitizenDifficulty: "easy", shortDescription: "A coastal Jyotirlinga and one of India’s most important Shiva pilgrimage sites." },
  { slug: "mallikarjuna", templeName: "Mallikarjuna Jyotirlinga", deityName: "Mallikarjuna Swamy", city: "Srisailam", state: "Andhra Pradesh", nearestAirport: "Hyderabad", nearestRailwayStation: "Markapur Road", bestTimeToVisit: "October to February", suggestedDuration: "2 days", nearbyPlaces: ["Srisailam Dam", "Pathala Ganga"], circuitSlug: "srisailam-spiritual-circuit", seniorCitizenDifficulty: "moderate", shortDescription: "A hill temple combining Jyotirlinga and Shakti Peetha significance." },
  { slug: "mahakaleshwar-ujjain", templeName: "Mahakaleshwar Jyotirlinga", deityName: "Mahakal", city: "Ujjain", state: "Madhya Pradesh", nearestAirport: "Indore", nearestRailwayStation: "Ujjain Junction", bestTimeToVisit: "October to March; Kumbh period by official schedule", suggestedDuration: "1–2 days", nearbyPlaces: ["Mahakal Lok", "Ram Ghat", "Kal Bhairav"], circuitSlug: "ujjain-omkareshwar-maheshwar", seniorCitizenDifficulty: "moderate", shortDescription: "Central to Ujjain pilgrimage and Simhastha Kumbh planning." },
  { slug: "omkareshwar", templeName: "Omkareshwar Jyotirlinga", deityName: "Omkareshwar Mahadev", city: "Omkareshwar", state: "Madhya Pradesh", nearestAirport: "Indore", nearestRailwayStation: "Omkareshwar Road / Indore", bestTimeToVisit: "October to March", suggestedDuration: "1 day", nearbyPlaces: ["Narmada ghats", "Mamleshwar", "Maheshwar"], circuitSlug: "ujjain-omkareshwar-maheshwar", seniorCitizenDifficulty: "moderate", shortDescription: "A Narmada island Jyotirlinga often combined with Ujjain." },
  { slug: "kedarnath", templeName: "Kedarnath Jyotirlinga", deityName: "Kedarnath Mahadev", city: "Kedarnath", state: "Uttarakhand", nearestAirport: "Dehradun", nearestRailwayStation: "Rishikesh / Haridwar", bestTimeToVisit: "Temple opening season, subject to weather", suggestedDuration: "3–5 days", nearbyPlaces: ["Gaurikund", "Sonprayag", "Triyuginarayan"], circuitSlug: "char-dham-yatra", seniorCitizenDifficulty: "difficult", shortDescription: "A high-altitude Jyotirlinga requiring careful health and route planning." },
  { slug: "bhimashankar", templeName: "Bhimashankar Jyotirlinga", deityName: "Bhimashankar Mahadev", city: "Bhimashankar", state: "Maharashtra", nearestAirport: "Pune", nearestRailwayStation: "Pune", bestTimeToVisit: "October to February", suggestedDuration: "1 day", nearbyPlaces: ["Pune", "Lonavala"], circuitSlug: "maharashtra-jyotirlinga-circuit", seniorCitizenDifficulty: "moderate", shortDescription: "A forested Western Ghats Jyotirlinga near Pune." },
  { slug: "kashi-vishwanath", templeName: "Kashi Vishwanath Jyotirlinga", deityName: "Vishwanath", city: "Varanasi", state: "Uttar Pradesh", nearestAirport: "Varanasi", nearestRailwayStation: "Varanasi Junction", bestTimeToVisit: "October to March", suggestedDuration: "2 days", nearbyPlaces: ["Dashashwamedh Ghat", "Sarnath"], circuitSlug: "varanasi-prayagraj-ayodhya", seniorCitizenDifficulty: "moderate", shortDescription: "One of India’s most visited Shiva temples in the sacred city of Kashi." },
  { slug: "trimbakeshwar", templeName: "Trimbakeshwar Jyotirlinga", deityName: "Trimbakeshwar Mahadev", city: "Trimbak / Nashik", state: "Maharashtra", nearestAirport: "Nashik / Mumbai", nearestRailwayStation: "Nashik Road", bestTimeToVisit: "October to March; Kumbh by official schedule", suggestedDuration: "1–2 days", nearbyPlaces: ["Nashik", "Godavari", "Shirdi"], circuitSlug: "nashik-trimbakeshwar-shirdi", seniorCitizenDifficulty: "moderate", shortDescription: "Key Jyotirlinga associated with Nashik-Trimbakeshwar Kumbh." },
  { slug: "vaidyanath", templeName: "Vaidyanath Jyotirlinga", deityName: "Baidyanath", city: "Deoghar", state: "Jharkhand", nearestAirport: "Deoghar", nearestRailwayStation: "Deoghar / Jasidih", bestTimeToVisit: "October to March", suggestedDuration: "1–2 days", nearbyPlaces: ["Basukinath"], circuitSlug: "deoghar-basukinath", seniorCitizenDifficulty: "easy", shortDescription: "A major Shiva pilgrimage centre in Deoghar." },
  { slug: "nageshwar", templeName: "Nageshwar Jyotirlinga", deityName: "Nageshwar Mahadev", city: "Dwarka", state: "Gujarat", nearestAirport: "Jamnagar / Rajkot", nearestRailwayStation: "Dwarka", bestTimeToVisit: "October to March", suggestedDuration: "1 day", nearbyPlaces: ["Dwarkadhish Temple", "Bet Dwarka"], circuitSlug: "somnath-dwarka-nageshwar", seniorCitizenDifficulty: "easy", shortDescription: "Often combined with Dwarka and Somnath in Gujarat circuits." },
  { slug: "rameshwaram", templeName: "Ramanathaswamy Jyotirlinga", deityName: "Rameshwaram", city: "Rameswaram", state: "Tamil Nadu", nearestAirport: "Madurai", nearestRailwayStation: "Rameswaram", bestTimeToVisit: "October to March", suggestedDuration: "2 days", nearbyPlaces: ["Dhanushkodi", "Madurai"], circuitSlug: "madurai-rameswaram-kanyakumari", seniorCitizenDifficulty: "easy", shortDescription: "A southern Jyotirlinga and one of India’s most important pilgrimage towns." },
  { slug: "grishneshwar", templeName: "Grishneshwar Jyotirlinga", deityName: "Grishneshwar Mahadev", city: "Verul / Ellora", state: "Maharashtra", nearestAirport: "Aurangabad", nearestRailwayStation: "Aurangabad", bestTimeToVisit: "October to March", suggestedDuration: "1 day", nearbyPlaces: ["Ellora Caves", "Daulatabad"], circuitSlug: "aurangabad-ellora-grishneshwar", seniorCitizenDifficulty: "easy", shortDescription: "A Jyotirlinga near Ellora Caves, useful for heritage-plus-pilgrimage trips." },
];

export function getJyotirlinga(slug: string) {
  return jyotirlingas.find((item) => item.slug === slug);
}
