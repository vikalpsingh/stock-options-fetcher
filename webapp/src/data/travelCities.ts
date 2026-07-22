export type TravelCity = {
  slug: string;
  cityName: string;
  state: string;
  country: string;
  aliases: string[];
  isKumbhCity: boolean;
  nearestAirportCode?: string;
  railwayStationCodes: string[];
  redbusCityId?: string;
  bookingSearchText?: string;
  flightAirportCode?: string;
  irctcSearchText?: string;
  priority: number;
};

const todo = (provider: string, city: string) => `TODO_VERIFY_${provider.toUpperCase()}_${city.toUpperCase()}_ID`;

export const travelCities: TravelCity[] = [
  { slug: "ujjain", cityName: "Ujjain", state: "Madhya Pradesh", country: "India", aliases: ["ujain", "mahakal"], isKumbhCity: true, nearestAirportCode: "IDR", railwayStationCodes: ["UJN"], redbusCityId: todo("redbus", "ujjain"), bookingSearchText: "Ujjain, Madhya Pradesh, India", flightAirportCode: "IDR", irctcSearchText: "Ujjain Junction", priority: 1 },
  { slug: "indore", cityName: "Indore", state: "Madhya Pradesh", country: "India", aliases: ["indhur"], isKumbhCity: false, nearestAirportCode: "IDR", railwayStationCodes: ["INDB"], redbusCityId: todo("redbus", "indore"), bookingSearchText: "Indore, Madhya Pradesh, India", flightAirportCode: "IDR", irctcSearchText: "Indore Junction", priority: 2 },
  { slug: "bhopal", cityName: "Bhopal", state: "Madhya Pradesh", country: "India", aliases: ["bpl"], isKumbhCity: false, nearestAirportCode: "BHO", railwayStationCodes: ["BPL"], redbusCityId: todo("redbus", "bhopal"), bookingSearchText: "Bhopal, Madhya Pradesh, India", flightAirportCode: "BHO", irctcSearchText: "Bhopal Junction", priority: 3 },
  { slug: "nashik", cityName: "Nashik", state: "Maharashtra", country: "India", aliases: ["nasik", "trimbakeshwar"], isKumbhCity: true, nearestAirportCode: "ISK", railwayStationCodes: ["NK"], redbusCityId: todo("redbus", "nashik"), bookingSearchText: "Nashik, Maharashtra, India", flightAirportCode: "ISK", irctcSearchText: "Nashik Road", priority: 4 },
  { slug: "prayagraj", cityName: "Prayagraj", state: "Uttar Pradesh", country: "India", aliases: ["allahabad", "sangam"], isKumbhCity: true, nearestAirportCode: "IXD", railwayStationCodes: ["PRYJ"], redbusCityId: todo("redbus", "prayagraj"), bookingSearchText: "Prayagraj, Uttar Pradesh, India", flightAirportCode: "IXD", irctcSearchText: "Prayagraj Junction", priority: 5 },
  { slug: "haridwar", cityName: "Haridwar", state: "Uttarakhand", country: "India", aliases: ["hardwar"], isKumbhCity: true, nearestAirportCode: "DED", railwayStationCodes: ["HW"], redbusCityId: todo("redbus", "haridwar"), bookingSearchText: "Haridwar, Uttarakhand, India", flightAirportCode: "DED", irctcSearchText: "Haridwar Junction", priority: 6 },
  { slug: "varanasi", cityName: "Varanasi", state: "Uttar Pradesh", country: "India", aliases: ["banaras", "kashi"], isKumbhCity: false, nearestAirportCode: "VNS", railwayStationCodes: ["BSB"], redbusCityId: todo("redbus", "varanasi"), bookingSearchText: "Varanasi, Uttar Pradesh, India", flightAirportCode: "VNS", irctcSearchText: "Varanasi Junction", priority: 7 },
  { slug: "delhi", cityName: "Delhi", state: "Delhi", country: "India", aliases: ["new delhi", "ncr"], isKumbhCity: false, nearestAirportCode: "DEL", railwayStationCodes: ["NDLS", "DLI"], redbusCityId: todo("redbus", "delhi"), bookingSearchText: "New Delhi, Delhi NCR, India", flightAirportCode: "DEL", irctcSearchText: "New Delhi", priority: 8 },
  { slug: "mumbai", cityName: "Mumbai", state: "Maharashtra", country: "India", aliases: ["bombay"], isKumbhCity: false, nearestAirportCode: "BOM", railwayStationCodes: ["MMCT", "CSMT", "LTT"], redbusCityId: todo("redbus", "mumbai"), bookingSearchText: "Mumbai, Maharashtra, India", flightAirportCode: "BOM", irctcSearchText: "Mumbai", priority: 9 },
  { slug: "pune", cityName: "Pune", state: "Maharashtra", country: "India", aliases: ["poona"], isKumbhCity: false, nearestAirportCode: "PNQ", railwayStationCodes: ["PUNE"], redbusCityId: todo("redbus", "pune"), bookingSearchText: "Pune, Maharashtra, India", flightAirportCode: "PNQ", irctcSearchText: "Pune Junction", priority: 10 },
  { slug: "bengaluru", cityName: "Bengaluru", state: "Karnataka", country: "India", aliases: ["bangalore", "blr"], isKumbhCity: false, nearestAirportCode: "BLR", railwayStationCodes: ["SBC", "YPR"], redbusCityId: todo("redbus", "bengaluru"), bookingSearchText: "Bengaluru, Karnataka, India", flightAirportCode: "BLR", irctcSearchText: "KSR Bengaluru", priority: 11 },
  { slug: "hyderabad", cityName: "Hyderabad", state: "Telangana", country: "India", aliases: ["secunderabad"], isKumbhCity: false, nearestAirportCode: "HYD", railwayStationCodes: ["HYB", "SC"], redbusCityId: todo("redbus", "hyderabad"), bookingSearchText: "Hyderabad, Telangana, India", flightAirportCode: "HYD", irctcSearchText: "Hyderabad", priority: 12 },
  { slug: "ahmedabad", cityName: "Ahmedabad", state: "Gujarat", country: "India", aliases: ["amdavad"], isKumbhCity: false, nearestAirportCode: "AMD", railwayStationCodes: ["ADI"], redbusCityId: todo("redbus", "ahmedabad"), bookingSearchText: "Ahmedabad, Gujarat, India", flightAirportCode: "AMD", irctcSearchText: "Ahmedabad Junction", priority: 13 },
  { slug: "jaipur", cityName: "Jaipur", state: "Rajasthan", country: "India", aliases: [], isKumbhCity: false, nearestAirportCode: "JAI", railwayStationCodes: ["JP"], redbusCityId: todo("redbus", "jaipur"), bookingSearchText: "Jaipur, Rajasthan, India", flightAirportCode: "JAI", irctcSearchText: "Jaipur", priority: 14 },
  { slug: "surat", cityName: "Surat", state: "Gujarat", country: "India", aliases: [], isKumbhCity: false, nearestAirportCode: "STV", railwayStationCodes: ["ST"], redbusCityId: todo("redbus", "surat"), bookingSearchText: "Surat, Gujarat, India", flightAirportCode: "STV", irctcSearchText: "Surat", priority: 15 },
  { slug: "nagpur", cityName: "Nagpur", state: "Maharashtra", country: "India", aliases: [], isKumbhCity: false, nearestAirportCode: "NAG", railwayStationCodes: ["NGP"], redbusCityId: todo("redbus", "nagpur"), bookingSearchText: "Nagpur, Maharashtra, India", flightAirportCode: "NAG", irctcSearchText: "Nagpur", priority: 16 },
  { slug: "shirdi", cityName: "Shirdi", state: "Maharashtra", country: "India", aliases: ["sai baba shirdi"], isKumbhCity: false, nearestAirportCode: "SAG", railwayStationCodes: ["SNSI"], redbusCityId: todo("redbus", "shirdi"), bookingSearchText: "Shirdi, Maharashtra, India", flightAirportCode: "SAG", irctcSearchText: "Sainagar Shirdi", priority: 17 },
];

export function getTravelCityBySlug(slug?: string) {
  if (!slug) return undefined;
  const normalized = slug.toLowerCase().trim();
  return travelCities.find((city) => city.slug === normalized || city.aliases.includes(normalized));
}

export function isVerifiedProviderId(value?: string) {
  return Boolean(value && !value.startsWith("TODO_VERIFY_"));
}
