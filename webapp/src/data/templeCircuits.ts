export type TempleCircuit = {
  slug: string;
  title: string;
  duration: string;
  statesCovered: string[];
  idealFor: string[];
  templesCovered: string[];
  startCity: string;
  endCity: string;
  travelModeRecommendations: string[];
  seniorCitizenSuitability: "easy" | "moderate" | "difficult";
  packageCTA: string;
};

export const templeCircuits: TempleCircuit[] = [
  { slug: "ujjain-omkareshwar-maheshwar", title: "Ujjain + Omkareshwar + Maheshwar", duration: "3–4 days", statesCovered: ["Madhya Pradesh"], idealFor: ["Jyotirlinga", "Narmada ghats", "family pilgrimage"], templesCovered: ["Mahakaleshwar", "Omkareshwar", "Mamleshwar"], startCity: "Indore", endCity: "Indore", travelModeRecommendations: ["Fly to Indore", "Use private cab for elders", "Keep Omkareshwar as a separate day"], seniorCitizenSuitability: "moderate", packageCTA: "Request MP Jyotirlinga package" },
  { slug: "nashik-trimbakeshwar-shirdi", title: "Nashik + Trimbakeshwar + Shirdi", duration: "3 days", statesCovered: ["Maharashtra"], idealFor: ["Nashik Kumbh", "Jyotirlinga", "Sai Baba darshan"], templesCovered: ["Trimbakeshwar", "Kalaram Temple", "Sai Baba Samadhi Mandir"], startCity: "Nashik", endCity: "Shirdi", travelModeRecommendations: ["Use Nashik as base", "Add Shirdi by road", "Verify Kumbh crowd controls"], seniorCitizenSuitability: "moderate", packageCTA: "Request Nashik-Shirdi package" },
  { slug: "varanasi-prayagraj-ayodhya", title: "Varanasi + Prayagraj + Ayodhya", duration: "5–6 days", statesCovered: ["Uttar Pradesh"], idealFor: ["Sangam", "Kashi Vishwanath", "Ram Mandir"], templesCovered: ["Kashi Vishwanath", "Triveni Sangam", "Ram Mandir"], startCity: "Varanasi", endCity: "Ayodhya", travelModeRecommendations: ["Train or road between cities", "Keep Varanasi ghats early morning", "Add rest day for elders"], seniorCitizenSuitability: "moderate", packageCTA: "Request UP sacred circuit package" },
  { slug: "somnath-dwarka-nageshwar", title: "Somnath + Dwarka + Nageshwar", duration: "4–5 days", statesCovered: ["Gujarat"], idealFor: ["Jyotirlinga", "Krishna pilgrimage", "coastal temples"], templesCovered: ["Somnath", "Dwarkadhish", "Nageshwar"], startCity: "Rajkot", endCity: "Jamnagar", travelModeRecommendations: ["Use road circuit", "Keep coastal travel buffers", "Avoid peak summer heat"], seniorCitizenSuitability: "easy", packageCTA: "Request Gujarat temple package" },
  { slug: "haridwar-rishikesh-char-dham-gateway", title: "Haridwar + Rishikesh + Char Dham Gateway", duration: "2–3 days before Char Dham", statesCovered: ["Uttarakhand"], idealFor: ["Ganga Aarti", "Char Dham preparation", "senior citizen acclimatisation"], templesCovered: ["Har Ki Pauri", "Rishikesh temples", "Neelkanth route"], startCity: "Haridwar", endCity: "Rishikesh", travelModeRecommendations: ["Arrive by train/flight via Dehradun", "Avoid same-day hill departure for elders"], seniorCitizenSuitability: "easy", packageCTA: "Request Char Dham gateway support" },
  { slug: "mathura-vrindavan-barsana", title: "Mathura + Vrindavan + Barsana", duration: "2–3 days", statesCovered: ["Uttar Pradesh"], idealFor: ["Krishna bhakti", "weekend pilgrimage", "family trip"], templesCovered: ["Banke Bihari", "Krishna Janmabhoomi", "Barsana temples"], startCity: "Mathura", endCity: "Vrindavan", travelModeRecommendations: ["Use Mathura rail access", "Plan early temple visits", "Avoid festival peak for elders"], seniorCitizenSuitability: "moderate", packageCTA: "Request Braj circuit package" },
  { slug: "puri-konark-bhubaneswar", title: "Puri + Konark + Bhubaneswar", duration: "3–4 days", statesCovered: ["Odisha"], idealFor: ["Jagannath darshan", "heritage", "family travel"], templesCovered: ["Jagannath Temple", "Konark Sun Temple", "Lingaraj Temple"], startCity: "Bhubaneswar", endCity: "Puri", travelModeRecommendations: ["Fly/train to Bhubaneswar", "Use Puri stay for Jagannath", "Keep Konark as half-day trip"], seniorCitizenSuitability: "easy", packageCTA: "Request Odisha pilgrimage package" },
  { slug: "madurai-rameswaram-kanyakumari", title: "Madurai + Rameswaram + Kanyakumari", duration: "4–5 days", statesCovered: ["Tamil Nadu"], idealFor: ["Jyotirlinga", "South India temples", "family itinerary"], templesCovered: ["Meenakshi Temple", "Ramanathaswamy Temple", "Kanyakumari Devi"], startCity: "Madurai", endCity: "Kanyakumari", travelModeRecommendations: ["Fly/train to Madurai", "Use road/train to Rameswaram", "Avoid aggressive one-day Rameswaram plans"], seniorCitizenSuitability: "easy", packageCTA: "Request South India temple package" },
];

export function getTempleCircuit(slug: string) {
  return templeCircuits.find((circuit) => circuit.slug === slug);
}
