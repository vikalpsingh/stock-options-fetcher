export type KumbhEvent = {
  slug: string;
  city: string;
  state: string;
  river: string;
  associatedTemple: string;
  eventYear?: number;
  status: "current_focus" | "next_focus" | "future" | "evergreen";
  dateStatus: "official" | "tentative" | "to_be_confirmed";
  keyDates: string;
  shortDescription: string;
  bestFor: string[];
  relatedGuides: { title: string; href: string }[];
};

export const kumbhEvents: KumbhEvent[] = [
  {
    slug: "nashik-kumbh-2027",
    city: "Nashik-Trimbakeshwar",
    state: "Maharashtra",
    river: "Godavari",
    associatedTemple: "Trimbakeshwar Jyotirlinga",
    eventYear: 2027,
    status: "current_focus",
    dateStatus: "to_be_confirmed",
    keyDates: "Official snan dates and arrangements should be verified with Maharashtra government and local authorities before travel.",
    shortDescription: "The nearer Kumbh focus for IndianKumbh.com, useful for families planning Nashik, Trimbakeshwar Jyotirlinga and Shirdi together.",
    bestFor: ["Trimbakeshwar Jyotirlinga", "Godavari snan", "Shirdi add-on", "Maharashtra family travel"],
    relatedGuides: [{ title: "Nashik + Trimbakeshwar + Shirdi", href: "/temple-circuits/nashik-trimbakeshwar-shirdi" }, { title: "Trimbakeshwar Jyotirlinga", href: "/12-jyotirlinga/trimbakeshwar" }],
  },
  {
    slug: "ujjain-kumbh-2028",
    city: "Ujjain",
    state: "Madhya Pradesh",
    river: "Shipra",
    associatedTemple: "Mahakaleshwar Jyotirlinga",
    eventYear: 2028,
    status: "next_focus",
    dateStatus: "tentative",
    keyDates: "Dates are tentative and subject to official confirmation by Madhya Pradesh authorities.",
    shortDescription: "A major pillar guide for Mahakal darshan, Shipra snan, Indore stay planning and nearby Jyotirlinga trips.",
    bestFor: ["Mahakal Darshan", "Shipra snan", "Indore hotel base", "Omkareshwar add-on"],
    relatedGuides: [{ title: "Mahakaleshwar Guide", href: "/12-jyotirlinga/mahakaleshwar-ujjain" }, { title: "Ujjain city guide", href: "/sacred-cities/ujjain" }],
  },
  {
    slug: "prayagraj-kumbh",
    city: "Prayagraj",
    state: "Uttar Pradesh",
    river: "Ganga, Yamuna and Saraswati Sangam",
    associatedTemple: "Triveni Sangam",
    status: "future",
    dateStatus: "to_be_confirmed",
    keyDates: "Future Kumbh and Ardh Kumbh schedules should be confirmed from official sources.",
    shortDescription: "Evergreen planning foundation for Sangam snan, Varanasi and Ayodhya add-ons.",
    bestFor: ["Sangam snan", "Varanasi extension", "Ayodhya route", "North India pilgrimage"],
    relatedGuides: [{ title: "Varanasi + Prayagraj + Ayodhya", href: "/temple-circuits/varanasi-prayagraj-ayodhya" }],
  },
  {
    slug: "haridwar-kumbh",
    city: "Haridwar",
    state: "Uttarakhand",
    river: "Ganga",
    associatedTemple: "Har Ki Pauri",
    status: "evergreen",
    dateStatus: "to_be_confirmed",
    keyDates: "Future Kumbh dates and crowd arrangements should be verified with official authorities.",
    shortDescription: "Ganga pilgrimage planning and Char Dham gateway guidance for families and senior citizens.",
    bestFor: ["Har Ki Pauri", "Ganga Aarti", "Rishikesh add-on", "Char Dham gateway"],
    relatedGuides: [{ title: "Haridwar + Rishikesh + Char Dham Gateway", href: "/temple-circuits/haridwar-rishikesh-char-dham-gateway" }],
  },
];

export function getKumbhEvent(slug: string) {
  return kumbhEvents.find((event) => event.slug === slug);
}
