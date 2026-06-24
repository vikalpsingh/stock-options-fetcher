export type PackageCategory = {
  slug: string;
  title: string;
  shortDescription: string;
  idealFor: string[];
  durationLabel: string;
  startingPriceLabel: string;
  inclusions: string[];
  exclusions: string[];
  ctaLabel: string;
  priority: number;
  destinationSlug: string;
};

const ujjainDestination = "ujjain-kumbh-2028";
const indicativePrice = "Indicative price on request";
const standardExclusions = [
  "Travel to the package starting point unless specifically quoted",
  "Personal expenses, meals or services not listed in the final quote",
  "Official darshan, snan and traffic arrangements not confirmed by authorities",
];

export const packageCategories = ([
  {
    slug: "mahakal-darshan-kumbh-snan",
    title: "Mahakal Darshan + Kumbh Snan Package",
    shortDescription: "A focused Ujjain pilgrimage plan combining Mahakaleshwar guidance, Shipra snan planning and practical local movement.",
    idealFor: ["First-time Ujjain visitors", "Couples", "Short spiritual trips"],
    durationLabel: "1–2 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Stay options as quoted", "Local transfer planning", "Mahakal and Shipra planning guidance"],
    exclusions: standardExclusions,
    ctaLabel: "Request Darshan Package Quote",
    priority: 1,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "ujjain-family-2n-3d",
    title: "2 Night / 3 Day Ujjain Family Package",
    shortDescription: "A balanced family itinerary with time for Mahakal darshan, selected temples, rest and local food.",
    idealFor: ["Families with children", "Working professionals", "First family pilgrimage"],
    durationLabel: "2 nights / 3 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Family stay options", "Station or bus-point transfer options", "Flexible Ujjain sightseeing plan"],
    exclusions: standardExclusions,
    ctaLabel: "Get Family Package Quote",
    priority: 2,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "indore-stay-ujjain-day-trip",
    title: "Indore Stay + Ujjain Kumbh Day Trip",
    shortDescription: "Use Indore for airport access and wider hotel choice, with a dedicated early transfer to Ujjain.",
    idealFor: ["Flight travellers", "Food lovers", "Visitors preferring Indore hotels"],
    durationLabel: "2–3 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Indore stay options", "Indore–Ujjain transfer options", "Darshan-day buffer guidance"],
    exclusions: standardExclusions,
    ctaLabel: "Compare Indore Base Packages",
    priority: 3,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "senior-citizen-assisted-yatra",
    title: "Senior Citizen Assisted Yatra Package",
    shortDescription: "A slower pilgrimage plan prioritising shorter transfers, rest windows and accessible stay requirements.",
    idealFor: ["Parents travelling with family", "Senior citizen groups", "Visitors needing a slower pace"],
    durationLabel: "2–4 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Accessible stay request", "Assisted local transfer request", "Rest-focused itinerary planning"],
    exclusions: [...standardExclusions, "Medical care, nursing or mobility equipment unless expressly confirmed"],
    ctaLabel: "Request Assisted Yatra Quote",
    priority: 4,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "premium-hotel-tent",
    title: "Premium Hotel / Tent Package",
    shortDescription: "Higher-comfort accommodation options with private transfers and flexible family travel planning.",
    idealFor: ["Premium family travellers", "Couples", "Visitors prioritising comfort"],
    durationLabel: "2–4 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Premium stay request", "Private transfer options", "Custom itinerary consultation"],
    exclusions: standardExclusions,
    ctaLabel: "Request Premium Stay Quote",
    priority: 5,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "budget-group-yatra",
    title: "Budget Group Yatra Package",
    shortDescription: "A cost-conscious group plan using shared transport and practical accommodation categories.",
    idealFor: ["Pilgrimage groups", "Friends and extended families", "Budget-conscious travellers"],
    durationLabel: "2–4 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Shared stay options", "Shared local transport request", "Group itinerary planning"],
    exclusions: [...standardExclusions, "Exclusive rooms or private vehicles unless separately quoted"],
    ctaLabel: "Get Group Yatra Quote",
    priority: 6,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "ujjain-omkareshwar-maheshwar",
    title: "Ujjain + Omkareshwar + Maheshwar Package",
    shortDescription: "A multi-city spiritual and Narmada circuit covering two Jyotirlingas and Maheshwar’s ghats.",
    idealFor: ["Jyotirlinga pilgrims", "Families with 4–5 days", "Spiritual circuit travellers"],
    durationLabel: "4 nights / 5 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Multi-city stay options", "Intercity transfer request", "Day-wise circuit planning"],
    exclusions: standardExclusions,
    ctaLabel: "Request Circuit Package Quote",
    priority: 7,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "corporate-society-group",
    title: "Corporate / Society Group Kumbh Package",
    shortDescription: "Coordinated travel planning for organised groups requiring rooms, vehicles and a clear operating schedule.",
    idealFor: ["Housing societies", "Corporate groups", "Religious organisations"],
    durationLabel: "Custom duration",
    startingPriceLabel: "Custom group quote",
    inclusions: ["Group rooming request", "Vehicle coordination request", "Group itinerary and arrival planning"],
    exclusions: [...standardExclusions, "Event permissions or special access unless confirmed in writing"],
    ctaLabel: "Request Group Proposal",
    priority: 8,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "women-family-safe-travel",
    title: "Women & Family Safe Travel Package",
    shortDescription: "A planning-first package request focused on verified stay requirements, daytime arrivals and dependable transfers.",
    idealFor: ["Women travellers", "Mothers with children", "Small family groups"],
    durationLabel: "2–4 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Verified-stay requirement", "Daytime transfer preference", "Family-focused itinerary request"],
    exclusions: [...standardExclusions, "Security guarantees beyond the partner’s confirmed service terms"],
    ctaLabel: "Request Family-Safe Quote",
    priority: 9,
    destinationSlug: ujjainDestination,
  },
  {
    slug: "nri-international-visitor",
    title: "NRI / International Visitor Kumbh Package",
    shortDescription: "An English-ready arrival and pilgrimage plan with airport transfers, cultural context and a slower orientation.",
    idealFor: ["NRIs", "International visitors", "First-time India pilgrimage travellers"],
    durationLabel: "4–7 days",
    startingPriceLabel: indicativePrice,
    inclusions: ["Airport transfer request", "English-speaking assistance request", "Cultural and practical orientation"],
    exclusions: [...standardExclusions, "Visa, insurance, international flights and foreign exchange"],
    ctaLabel: "Request International Visitor Quote",
    priority: 10,
    destinationSlug: ujjainDestination,
  },
] satisfies PackageCategory[]).sort((a, b) => a.priority - b.priority);

export function getPackageCategory(slug: string) {
  return packageCategories.find((category) => category.slug === slug);
}

export function getPackagesForDestination(destinationSlug: string) {
  return packageCategories.filter((category) => category.destinationSlug === destinationSlug);
}

