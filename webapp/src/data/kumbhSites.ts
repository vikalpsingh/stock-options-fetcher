export type KumbhSiteStatus = "featured" | "upcoming" | "evergreen";

export type KumbhSite = {
  slug: string;
  name: string;
  city: string;
  state: string;
  river: string;
  nextEventName: string;
  nextEventYear: number | null;
  tentativeDates: string;
  status: KumbhSiteStatus;
  shortDescription: string;
  keyAttractions: string[];
  mainCTA: string;
  imageAlt: string;
  priority: number;
};

export const kumbhSites = ([
  {
    slug: "ujjain-kumbh-2028",
    name: "Ujjain Simhastha Kumbh 2028",
    city: "Ujjain",
    state: "Madhya Pradesh",
    river: "Shipra",
    nextEventName: "Ujjain Simhastha Kumbh",
    nextEventYear: 2028,
    tentativeDates: "Tentative 2028 planning window — exact dates are subject to official confirmation.",
    status: "featured",
    shortDescription: "IndianKumbh's primary guide for Mahakal darshan, stays, routes, food, nearby trips and family itineraries.",
    keyAttractions: ["Mahakaleshwar Jyotirlinga", "Shipra ghats", "Mahakal Lok", "Ujjain temple circuit"],
    mainCTA: "Plan Ujjain Trip",
    imageAlt: "Devotees and temples beside the Shipra ghats during a spiritual gathering in Ujjain",
    priority: 1,
  },
  {
    slug: "nashik-kumbh-2027",
    name: "Nashik–Trimbakeshwar Kumbh 2027",
    city: "Nashik–Trimbakeshwar",
    state: "Maharashtra",
    river: "Godavari",
    nextEventName: "Nashik–Trimbakeshwar Kumbh",
    nextEventYear: 2027,
    tentativeDates: "Expected in 2027 — detailed dates and arrangements await official publication.",
    status: "upcoming",
    shortDescription: "A practical overview for the twin-city pilgrimage and Trimbakeshwar Jyotirlinga circuit.",
    keyAttractions: ["Trimbakeshwar Jyotirlinga", "Ram Kund", "Godavari ghats", "Panchavati"],
    mainCTA: "Explore Nashik 2027",
    imageAlt: "Godavari pilgrimage ghats and temple landscape in Nashik and Trimbakeshwar",
    priority: 2,
  },
  {
    slug: "prayagraj-kumbh",
    name: "Prayagraj Kumbh",
    city: "Prayagraj",
    state: "Uttar Pradesh",
    river: "Ganga–Yamuna Sangam",
    nextEventName: "Future Prayagraj Kumbh / Ardh Kumbh Guide",
    nextEventYear: null,
    tentativeDates: "Future schedule not yet confirmed — verify the event name and dates after official announcement.",
    status: "evergreen",
    shortDescription: "An evergreen planning foundation for future Prayagraj Kumbh and Ardh Kumbh journeys.",
    keyAttractions: ["Triveni Sangam", "Akshayavat", "Bade Hanuman Temple", "Sangam boat routes"],
    mainCTA: "Explore Prayagraj Guide",
    imageAlt: "Pilgrimage boats and sacred bathing activity at the Triveni Sangam in Prayagraj",
    priority: 3,
  },
  {
    slug: "haridwar-kumbh",
    name: "Haridwar Kumbh",
    city: "Haridwar",
    state: "Uttarakhand",
    river: "Ganga",
    nextEventName: "Future Haridwar Kumbh Guide",
    nextEventYear: null,
    tentativeDates: "Future schedule not yet confirmed — dates and local arrangements await official publication.",
    status: "evergreen",
    shortDescription: "An evergreen foundation for Har Ki Pauri, Ganga pilgrimage, rail access and future Kumbh planning.",
    keyAttractions: ["Har Ki Pauri", "Ganga Aarti", "Mansa Devi", "Chandi Devi"],
    mainCTA: "Explore Haridwar Guide",
    imageAlt: "Har Ki Pauri ghats and Ganga Aarti pilgrimage scene in Haridwar",
    priority: 4,
  },
] satisfies KumbhSite[]).sort((a, b) => a.priority - b.priority);

export function getKumbhSite(slug: string) {
  return kumbhSites.find((site) => site.slug === slug);
}
