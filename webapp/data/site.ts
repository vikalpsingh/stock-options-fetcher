import {
  BedDouble,
  BusFront,
  Clock3,
  Compass,
  Footprints,
  Landmark,
  MapPinned,
  ShieldCheck,
  Soup,
  Sparkles,
} from "lucide-react";

export const navItems = [
  { href: "/kumbh-2028-guide", label: "Kumbh 2028" },
  { href: "/how-to-reach", label: "How to reach" },
  { href: "/mahakal-temple-guide", label: "Mahakal" },
  { href: "/stay-guide", label: "Stay" },
  { href: "/nearby-places", label: "Explore" },
  { href: "/itineraries", label: "Itineraries" },
];

export const quickGuides = [
  {
    href: "/how-to-reach",
    title: "Reach Ujjain",
    text: "Compare train, flight, road and local transfers.",
    icon: BusFront,
    meta: "Routes & transfers",
  },
  {
    href: "/mahakal-temple-guide",
    title: "Mahakal Darshan",
    text: "Plan timings, entry, Bhasma Aarti and temple etiquette.",
    icon: Landmark,
    meta: "Temple guide",
  },
  {
    href: "/stay-guide",
    title: "Choose your stay",
    text: "Stay smart across Ujjain, Indore and Bhopal.",
    icon: BedDouble,
    meta: "3 city comparison",
  },
  {
    href: "/nearby-places",
    title: "Go beyond Ujjain",
    text: "Add Omkareshwar, Mandu, Indore or Bhopal.",
    icon: Compass,
    meta: "Easy side trips",
  },
];

export const highlights = [
  { value: "12", label: "Jyotirlingas: Mahakal is one", icon: Sparkles },
  { value: "55 km", label: "From Indore airport", icon: MapPinned },
  { value: "24/7", label: "Practical trip guidance", icon: Clock3 },
  { value: "2–7 days", label: "Flexible itineraries", icon: Footprints },
];

export const pageContent = {
  "/kumbh-2028-guide": {
    eyebrow: "The essential guide",
    title: "Ujjain Kumbh Mela 2028",
    intro:
      "Understand the festival, choose the right travel window, and arrive prepared for one of India’s most extraordinary spiritual gatherings.",
    sections: [
      {
        title: "What is Simhastha?",
        text: "Ujjain’s Kumbh is traditionally known as Simhastha. The city gathers around the Shipra river for sacred bathing, darshan, discourses and processions. Official 2028 dates and arrangements should always be reconfirmed from government sources before booking.",
      },
      {
        title: "When should you visit?",
        text: "Royal bathing days carry the greatest spiritual significance and the largest crowds. For a gentler first visit, consider the days around major bathing dates and reserve at least three nights.",
      },
      {
        title: "Prepare for peak crowds",
        text: "Keep plans flexible, travel light, save offline copies of bookings, carry water and medicines, and agree on a family meeting point before entering busy zones.",
      },
    ],
    tips: ["Book refundable travel first", "Use official transport advisories", "Carry a small day bag", "Keep ID and emergency contacts offline"],
    icon: Sparkles,
  },
  "/how-to-reach": {
    eyebrow: "Routes made simple",
    title: "How to reach Ujjain",
    intro: "Choose the most practical route by air, rail or road—with realistic transfer time built in.",
    sections: [
      { title: "By air", text: "Devi Ahilyabai Holkar Airport in Indore is the nearest major airport, roughly 55 km from Ujjain. Allow extra transfer time during festival traffic." },
      { title: "By train", text: "Ujjain Junction connects with major cities including Delhi, Mumbai, Ahmedabad, Jaipur, Bhopal and Indore. Book early and keep a waitlist backup." },
      { title: "By road", text: "Ujjain is well connected to Indore, Bhopal, Omkareshwar and other Madhya Pradesh destinations by bus and taxi." },
    ],
    tips: ["Indore airport → Ujjain: about 1.5–2.5 hours", "Indore → Ujjain: about 1–2 hours", "Bhopal → Ujjain: about 4–5 hours", "Add a festival-day buffer"],
    icon: BusFront,
  },
  "/mahakal-temple-guide": {
    eyebrow: "Darshan with confidence",
    title: "Mahakaleshwar temple guide",
    intro: "A calm, practical guide to darshan, Bhasma Aarti, temple customs and the Mahakal Lok corridor.",
    sections: [
      { title: "Darshan planning", text: "Start early and use only official temple booking channels. Queue arrangements can change during Simhastha, weekends and festivals." },
      { title: "Bhasma Aarti", text: "The pre-dawn ritual is deeply revered and generally requires advance registration, identity verification and specific dress guidance. Reconfirm every requirement before your visit." },
      { title: "Mahakal Lok", text: "The corridor is best explored in the evening light. Keep separate time for the temple queue and the public promenade." },
    ],
    tips: ["Dress modestly", "Keep footwear at designated counters", "Avoid unofficial agents", "Check camera and bag rules"],
    icon: Landmark,
  },
  "/stay-guide": {
    eyebrow: "Sleep better, travel smarter",
    title: "Where to stay",
    intro: "Balance convenience, comfort and price across Ujjain, Indore and Bhopal.",
    sections: [
      { title: "Ujjain", text: "Best for early darshan and full immersion. Expect high demand, traffic controls and simpler rooms near the pilgrimage zone." },
      { title: "Indore", text: "Best for airport access, broader hotel choice and excellent food. Daily travel to Ujjain can be tiring on peak days." },
      { title: "Bhopal", text: "Best as part of a longer Madhya Pradesh itinerary. It is too far for a comfortable daily Kumbh commute." },
    ],
    tips: ["Prioritize walkability", "Confirm vehicle access", "Ask about power backup", "Choose refundable rates"],
    icon: BedDouble,
  },
  "/nearby-places": {
    eyebrow: "Extend the journey",
    title: "Nearby places worth adding",
    intro: "Turn your pilgrimage into a richer Madhya Pradesh journey with easy, well-paced side trips.",
    sections: [
      { title: "Indore · 55 km", text: "Street food, Rajwada and airport convenience make Indore the easiest add-on before or after Ujjain." },
      { title: "Omkareshwar · 140 km", text: "Combine two Jyotirlingas in one journey. Plan a full day or an overnight stop rather than rushing." },
      { title: "Mandu & Maheshwar", text: "Add architecture, Narmada ghats, weaving traditions and a slower rhythm to a 5–7 day itinerary." },
    ],
    tips: ["Indore: 1 day", "Omkareshwar: 1–2 days", "Mandu: 1 day", "Maheshwar: 1–2 days"],
    icon: Compass,
  },
  "/food-guide": {
    eyebrow: "A delicious detour",
    title: "What to eat in Ujjain",
    intro: "A practical vegetarian food trail—from poha at sunrise to comforting dal bafla.",
    sections: [
      { title: "Breakfast", text: "Start with poha, jalebi, kachori or sabudana khichdi. Choose busy stalls where food turns over quickly." },
      { title: "Local favourites", text: "Try dal bafla, bhutte ka kees, seasonal thalis and fresh lassi. Ask about spice levels if you prefer mild food." },
      { title: "Festival food safety", text: "Drink sealed or filtered water, prefer freshly cooked hot food and carry oral rehydration salts." },
    ],
    tips: ["Eat freshly cooked food", "Carry a reusable bottle", "Check fasting ingredients", "Keep small cash"],
    icon: Soup,
  },
  "/itineraries": {
    eyebrow: "Ready-to-use plans",
    title: "Itineraries for every pace",
    intro: "Use these balanced plans as a starting point, then personalize them in the trip planner.",
    sections: [
      { title: "2 days · Ujjain essential", text: "Day 1: Mahakal darshan, Mahakal Lok and old city. Day 2: Shipra ghats, Kal Bhairav, Harsiddhi and a relaxed departure." },
      { title: "4 days · Ujjain + Indore", text: "Spend two full days in Ujjain, then add Rajwada, Chappan Dukan and Sarafa in Indore." },
      { title: "7 days · Sacred Madhya Pradesh", text: "Combine Ujjain, Indore, Omkareshwar, Maheshwar and Mandu with humane travel days." },
    ],
    tips: ["Keep darshan morning flexible", "Avoid same-day flight after a peak event", "Add rest after long queues", "Share the plan on WhatsApp"],
    icon: Footprints,
  },
};

export const faqs = [
  { q: "When is Ujjain Kumbh Mela 2028?", a: "The detailed official event and bathing-day calendar should be confirmed from Madhya Pradesh government and district administration announcements before you book." },
  { q: "Which airport is closest to Ujjain?", a: "Indore’s Devi Ahilyabai Holkar Airport is the nearest major airport, approximately 55 km away." },
  { q: "How many days are enough for Ujjain?", a: "Two full days suit the key temples and ghats. During Kumbh, three or more nights provide a safer buffer for crowds and traffic." },
  { q: "Is Ujjain suitable for international visitors?", a: "Yes. Carry identification, dress respectfully at religious sites, arrange reliable transport, and keep offline translations and booking copies." },
  { q: "Should I stay in Ujjain or Indore?", a: "Stay in Ujjain for early darshan and festival access. Choose Indore for airport convenience, wider hotel options and food, while allowing extra commute time." },
  { q: "Is the Bhasma Aarti free?", a: "Rules and booking categories can change. Use only the official Mahakaleshwar temple portal and verify current ID, dress and entry requirements." },
];

export const safetyPoints = [
  { title: "Stay together", text: "Pick a meeting point and share accommodation details.", icon: ShieldCheck },
  { title: "Walk prepared", text: "Wear broken-in footwear and carry water.", icon: Footprints },
  { title: "Save offline", text: "Keep tickets, ID copies and maps available without data.", icon: MapPinned },
];
