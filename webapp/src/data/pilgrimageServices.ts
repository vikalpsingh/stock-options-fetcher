export type PilgrimageServiceGroup = {
  pillar: "char-dham" | "jyotirlinga";
  title: string;
  items: string[];
  note: string;
};

export const pilgrimageServices: PilgrimageServiceGroup[] = [
  { pillar: "char-dham", title: "Registration and official rules", items: ["Official yatra registration", "Vehicle registration", "Health advisories", "Helicopter booking reference", "Weather alerts"], note: "Verify everything through official Uttarakhand portals before travel." },
  { pillar: "jyotirlinga", title: "Darshan and temple rules", items: ["Temple-specific darshan booking", "Official temple trust links placeholder", "Aarti booking placeholder", "Festival crowd rules"], note: "Rules vary by temple and season." },
  { pillar: "char-dham", title: "Accommodation", items: ["Hotels", "Dharamshala", "Ashram stay", "Group stay", "Senior citizen-friendly stay"], note: "Book early and keep refundable options." },
  { pillar: "jyotirlinga", title: "Accommodation", items: ["Hotels", "Dharamshala", "Ashram stay", "Group stay", "Temple-city stay"], note: "Stay near temple for darshan or in a comfortable city hotel for elders." },
  { pillar: "char-dham", title: "Transport", items: ["Flights", "Trains", "Buses", "Local taxi", "Shared jeeps", "Last-mile walking/trekking"], note: "Hill roads, weather and route status can change quickly." },
  { pillar: "jyotirlinga", title: "Transport", items: ["Flights", "Trains", "Buses", "Local taxi", "Regional circuits"], note: "Most Jyotirlinga trips work best as regional circuits." },
  { pillar: "char-dham", title: "Medical and emergency", items: ["Senior citizen checklist", "Altitude caution", "Medicine kit", "Ambulance placeholder", "Weather/landslide caution"], note: "Health planning is essential for Kedarnath and Yamunotri." },
  { pillar: "jyotirlinga", title: "Medical and emergency", items: ["Senior citizen checklist", "Medicine kit", "Crowd caution", "Emergency contacts placeholder"], note: "Avoid peak festival days if travelling with elders." },
  { pillar: "char-dham", title: "Food, water and sanitation", items: ["Satvik food", "Hydration", "Safe food advice", "Toilet checklist", "Hygiene tips"], note: "Carry essentials during long hill transfers." },
  { pillar: "jyotirlinga", title: "Food, water and sanitation", items: ["Satvik food", "Local food", "Hydration", "Safe food advice", "Public toilet placeholder"], note: "Eat light before long queues or temple visits." },
  { pillar: "char-dham", title: "Package support", items: ["Senior citizen yatra", "Family package", "Group yatra", "Premium assisted yatra", "Budget yatra"], note: "Packages are fulfilled by independent partners." },
  { pillar: "jyotirlinga", title: "Package support", items: ["Regional circuit", "Family trip", "Group yatra", "Senior citizen yatra"], note: "Plan by region rather than rushing all 12." },
];

export function getPilgrimageServices(pillar: PilgrimageServiceGroup["pillar"]) {
  return pilgrimageServices.filter((group) => group.pillar === pillar);
}
