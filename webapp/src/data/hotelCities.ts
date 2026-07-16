export type HotelCity = {
  slug: string;
  cityName: string;
  state: string;
  country: string;
  bookingSearchText: string;
  defaultNights: number;
  isKumbhCity: boolean;
  nearbyAirport: string;
  recommendedFor: string;
  priority: number;
};

export const hotelCities: HotelCity[] = [
  {
    slug: "ujjain",
    cityName: "Ujjain",
    state: "Madhya Pradesh",
    country: "India",
    bookingSearchText: "Ujjain, Madhya Pradesh, India",
    defaultNights: 1,
    isKumbhCity: true,
    nearbyAirport: "Indore",
    recommendedFor: "Mahakal darshan, Kumbh snan, short pilgrimage stay",
    priority: 1,
  },
  {
    slug: "indore",
    cityName: "Indore",
    state: "Madhya Pradesh",
    country: "India",
    bookingSearchText: "Indore, Madhya Pradesh, India",
    defaultNights: 2,
    isKumbhCity: false,
    nearbyAirport: "Indore",
    recommendedFor: "Family comfort, airport access, better hotel choice, Ujjain day trip",
    priority: 2,
  },
  {
    slug: "bhopal",
    cityName: "Bhopal",
    state: "Madhya Pradesh",
    country: "India",
    bookingSearchText: "Bhopal, Madhya Pradesh, India",
    defaultNights: 2,
    isKumbhCity: false,
    nearbyAirport: "Bhopal",
    recommendedFor: "Extended MP itinerary, Sanchi, Omkareshwar add-on",
    priority: 3,
  },
  {
    slug: "nashik",
    cityName: "Nashik",
    state: "Maharashtra",
    country: "India",
    bookingSearchText: "Nashik, Maharashtra, India",
    defaultNights: 2,
    isKumbhCity: true,
    nearbyAirport: "Nashik / Mumbai",
    recommendedFor: "Nashik-Trimbakeshwar Kumbh planning, Trimbakeshwar Jyotirlinga, family stay",
    priority: 4,
  },
  {
    slug: "prayagraj",
    cityName: "Prayagraj",
    state: "Uttar Pradesh",
    country: "India",
    bookingSearchText: "Prayagraj, Uttar Pradesh, India",
    defaultNights: 2,
    isKumbhCity: true,
    nearbyAirport: "Prayagraj / Varanasi / Lucknow",
    recommendedFor: "Sangam snan, future Kumbh and Ardh Kumbh planning",
    priority: 5,
  },
  {
    slug: "haridwar",
    cityName: "Haridwar",
    state: "Uttarakhand",
    country: "India",
    bookingSearchText: "Haridwar, Uttarakhand, India",
    defaultNights: 2,
    isKumbhCity: true,
    nearbyAirport: "Dehradun",
    recommendedFor: "Ganga snan, Har Ki Pauri, future Haridwar Kumbh planning",
    priority: 6,
  },
  {
    slug: "varanasi",
    cityName: "Varanasi",
    state: "Uttar Pradesh",
    country: "India",
    bookingSearchText: "Varanasi, Uttar Pradesh, India",
    defaultNights: 2,
    isKumbhCity: false,
    nearbyAirport: "Varanasi",
    recommendedFor: "Spiritual extension, Kashi Vishwanath, family pilgrimage add-on",
    priority: 7,
  },
  {
    slug: "omkareshwar",
    cityName: "Omkareshwar",
    state: "Madhya Pradesh",
    country: "India",
    bookingSearchText: "Omkareshwar, Madhya Pradesh, India",
    defaultNights: 1,
    isKumbhCity: false,
    nearbyAirport: "Indore",
    recommendedFor: "Jyotirlinga circuit, Narmada stay, slower pilgrimage extension",
    priority: 8,
  },
  {
    slug: "maheshwar",
    cityName: "Maheshwar",
    state: "Madhya Pradesh",
    country: "India",
    bookingSearchText: "Maheshwar, Madhya Pradesh, India",
    defaultNights: 1,
    isKumbhCity: false,
    nearbyAirport: "Indore",
    recommendedFor: "Narmada ghats, heritage stay, Maheshwar-Mandu extension",
    priority: 9,
  },
];

export function getHotelCityBySlug(slug: string) {
  return hotelCities.find((city) => city.slug === slug);
}
