export type KumbhGuide = {
  slug: string;
  title: string;
  shortTitle: string;
  city: string;
  state: string;
  river: string;
  associatedTemple: string;
  status: "current_focus" | "next_focus" | "future";
  eventYear: string;
  dateStatus: "official" | "tentative" | "to_be_confirmed";
  heroTitle: string;
  heroSubtitle: string;
  spiritualSignificance: string[];
  mythologyStories: { title: string; summary: string }[];
  historicalTimeline: { period: string; title: string; description: string }[];
  lastKumbhStats: {
    previousEventYear: string;
    estimatedPilgrims: string;
    duration: string;
    infrastructureNotes: string;
    crowdNotes: string;
    sourceNote: string;
    confidenceLevel: "official" | "media_estimate" | "editorial_estimate";
  };
  famousNamesAndInstitutions: { name: string; role: string; relevance: string }[];
  keyPlaces: {
    name: string;
    type: "temple" | "ghat" | "river" | "city_area" | "nearby_destination" | "service_area";
    importance: string;
    travellerTip: string;
    bestTimeToVisit: string;
    seniorCitizenSuitability: "easy" | "moderate" | "difficult";
    suggestedDuration: string;
    nearbyPlaces: string[];
    tags: string[];
  }[];
  usefulServices: { title: string; description: string; priority: number }[];
  travellerWarnings: string[];
  seniorCitizenTips: string[];
  familyTips: string[];
  seoKeywords: string[];
};

const kumbhOrigin = {
  title: "Samudra Manthan and the Amrit Kalash",
  summary: "Traditional Kumbh belief connects the festival with the churning of the cosmic ocean, when devas and asuras sought amrit. Sacred drops are believed to be associated with the four Kumbh places. These stories are presented as traditional religious beliefs.",
};

export const kumbhGuides: KumbhGuide[] = [
  {
    slug: "nashik-kumbh-2027",
    title: "Nashik-Trimbakeshwar Kumbh 2027 Guide",
    shortTitle: "Nashik Kumbh 2027",
    city: "Nashik and Trimbakeshwar",
    state: "Maharashtra",
    river: "Godavari",
    associatedTemple: "Trimbakeshwar Jyotirlinga",
    status: "current_focus",
    eventYear: "2027",
    dateStatus: "to_be_confirmed",
    heroTitle: "Nashik-Trimbakeshwar Kumbh 2027 Guide",
    heroSubtitle: "Plan your Nashik Kumbh yatra with practical guidance on Trimbakeshwar Jyotirlinga, Ramkund, Godavari snan, stay, routes, packages and senior citizen travel.",
    spiritualSignificance: ["One of the four sacred Kumbh locations in India.", "Connected with the Godavari river, Ramkund and Trimbakeshwar Jyotirlinga.", "Useful for combining Kumbh snan, Jyotirlinga darshan and Shirdi in one Maharashtra pilgrimage."],
    mythologyStories: [kumbhOrigin, { title: "Godavari, Trimbakeshwar and Panchavati", summary: "Nashik pilgrimage is closely associated with the Godavari river, Trimbakeshwar Jyotirlinga and the Ramayana-linked Panchavati area." }],
    historicalTimeline: [
      { period: "Traditional belief", title: "Kumbh origin", description: "Kumbh Mela is traditionally linked with the Amrit Kalash story from Samudra Manthan." },
      { period: "2015", title: "Previous Nashik-Trimbakeshwar Simhastha", description: "Large-scale dual-location planning across Nashik city and Trimbakeshwar shaped modern traveller expectations." },
      { period: "2027", title: "Upcoming focus", description: "Dates, bathing days, routes and services should be treated as to be confirmed until official announcements." },
    ],
    lastKumbhStats: { previousEventYear: "2015", estimatedPilgrims: "Very large pilgrim gathering; exact figures vary by source", duration: "Festival period across Nashik and Trimbakeshwar", infrastructureNotes: "Infrastructure, security, water, transport and sanitation planning were critical because Nashik and Trimbakeshwar function as linked but separate zones.", crowdNotes: "Ramkund and Trimbakeshwar/Kushavarta can have different crowd patterns, so travellers should not plan them casually on peak days.", sourceNote: "Visitor estimates vary by source. Verify official figures before final publication. Verify current official dates, bathing dates, traffic rules and accommodation arrangements before publishing final content.", confidenceLevel: "editorial_estimate" },
    famousNamesAndInstitutions: [
      { name: "Akhara traditions", role: "Religious institutions", relevance: "Central to Kumbh processions, bathing order and spiritual camps." },
      { name: "Naga sadhus", role: "Ascetic traditions", relevance: "Associated with renunciation and akhara processions." },
      { name: "Trimbakeshwar Jyotirlinga", role: "Main temple", relevance: "A major Shiva pilgrimage anchor near Nashik." },
    ],
    keyPlaces: [
      { name: "Ramkund", type: "ghat", importance: "Important Godavari snan area in Nashik.", travellerTip: "Expect crowd controls near peak bathing days; keep elders close and avoid rushing.", bestTimeToVisit: "Early morning on non-peak days", seniorCitizenSuitability: "moderate", suggestedDuration: "1–2 hours", nearbyPlaces: ["Panchavati", "Kalaram Mandir"], tags: ["must_visit", "near_main_kumbh_area", "family_friendly"] },
      { name: "Godavari River Ghats", type: "river", importance: "Sacred riverfront for Nashik Kumbh rituals.", travellerTip: "Use official entry/exit routes when published.", bestTimeToVisit: "Morning or evening", seniorCitizenSuitability: "moderate", suggestedDuration: "1–2 hours", nearbyPlaces: ["Ramkund"], tags: ["must_visit", "near_main_kumbh_area"] },
      { name: "Trimbakeshwar Jyotirlinga", type: "temple", importance: "One of the 12 Jyotirlingas and key anchor of Nashik Kumbh.", travellerTip: "Plan Nashik and Trimbakeshwar as separate movement zones.", bestTimeToVisit: "Early morning, rules permitting", seniorCitizenSuitability: "moderate", suggestedDuration: "Half day", nearbyPlaces: ["Kushavarta Kund"], tags: ["must_visit", "jyotirlinga", "family_friendly"] },
      { name: "Kushavarta Kund", type: "ghat", importance: "Sacred kund at Trimbakeshwar linked with Godavari origin traditions.", travellerTip: "Crowd pattern can differ from Nashik city ghats.", bestTimeToVisit: "Morning", seniorCitizenSuitability: "moderate", suggestedDuration: "1 hour", nearbyPlaces: ["Trimbakeshwar Jyotirlinga"], tags: ["must_visit", "jyotirlinga"] },
      { name: "Panchavati", type: "city_area", importance: "Ramayana-linked area of Nashik.", travellerTip: "Good for families if planned outside peak heat and crowd hours.", bestTimeToVisit: "Morning", seniorCitizenSuitability: "easy", suggestedDuration: "2–3 hours", nearbyPlaces: ["Kalaram Mandir", "Sita Gufa"], tags: ["family_friendly", "near_main_kumbh_area"] },
      { name: "Kalaram Mandir", type: "temple", importance: "Important temple in Panchavati.", travellerTip: "Combine with Panchavati and Sita Gufa.", bestTimeToVisit: "Morning/evening", seniorCitizenSuitability: "easy", suggestedDuration: "45–60 minutes", nearbyPlaces: ["Panchavati"], tags: ["family_friendly"] },
      { name: "Sita Gufa", type: "temple", importance: "Ramayana-linked devotional stop.", travellerTip: "Check accessibility if travelling with elders.", bestTimeToVisit: "Morning", seniorCitizenSuitability: "moderate", suggestedDuration: "45 minutes", nearbyPlaces: ["Panchavati"], tags: ["family_friendly"] },
      { name: "Shirdi", type: "nearby_destination", importance: "Popular Sai Baba pilgrimage add-on.", travellerTip: "Best planned as a separate day or overnight extension.", bestTimeToVisit: "Any season with advance booking", seniorCitizenSuitability: "easy", suggestedDuration: "1 day", nearbyPlaces: ["Nashik"], tags: ["nearby_add_on", "family_friendly"] },
      { name: "Anjaneri", type: "nearby_destination", importance: "Hill and devotional area near Trimbakeshwar.", travellerTip: "Not ideal for all elders; check walking difficulty.", bestTimeToVisit: "Cooler months", seniorCitizenSuitability: "difficult", suggestedDuration: "Half day", nearbyPlaces: ["Trimbakeshwar"], tags: ["nearby_add_on"] },
      { name: "Sula / Nashik city hotel zone", type: "service_area", importance: "Practical stay and hotel area for families.", travellerTip: "Use Nashik city for broader hotel choice and local transport.", bestTimeToVisit: "Stay base", seniorCitizenSuitability: "easy", suggestedDuration: "Base area", nearbyPlaces: ["Ramkund", "Panchavati"], tags: ["senior_friendly", "family_friendly"] },
    ],
    usefulServices: ["Accommodation", "City transport", "Bus booking", "Train routes", "Medical camps", "Police/helpdesk", "Lost and found", "Drinking water", "Toilets", "Cloakroom/luggage advice", "Senior citizen assistance", "Group travel support", "Package quote"].map((title, index) => ({ title, description: `${title} information should be verified and updated as official Nashik Kumbh arrangements are announced.`, priority: index + 1 })),
    travellerWarnings: ["Nashik city and Trimbakeshwar are separate planning zones.", "Ramkund and Kushavarta Kund may need different movement planning.", "Shirdi can be combined, but avoid overpacking the same day."],
    seniorCitizenTips: ["Prefer Nashik city hotels with lift/vehicle access.", "Keep Trimbakeshwar as a separate slow half-day or full-day plan.", "Avoid peak heat and peak bathing rush where possible."],
    familyTips: ["Fix one meeting point before entering crowded ghats.", "Keep children’s IDs and hotel details offline.", "Plan meals and toilet breaks before long queues."],
    seoKeywords: ["Nashik Kumbh 2027", "Trimbakeshwar Kumbh", "Nashik Simhastha", "Godavari Kumbh", "Ramkund Nashik"],
  },
  {
    slug: "ujjain-kumbh-2028",
    title: "Ujjain Simhastha Kumbh 2028 Guide",
    shortTitle: "Ujjain Kumbh 2028",
    city: "Ujjain",
    state: "Madhya Pradesh",
    river: "Shipra",
    associatedTemple: "Mahakaleshwar Jyotirlinga",
    status: "next_focus",
    eventYear: "2028",
    dateStatus: "tentative",
    heroTitle: "Ujjain Simhastha Kumbh 2028 Guide",
    heroSubtitle: "Plan Ujjain Simhastha Kumbh with practical information on Mahakaleshwar Jyotirlinga, Shipra snan, Ram Ghat, stay in Ujjain vs Indore, routes, packages and senior citizen travel.",
    spiritualSignificance: ["One of the four sacred Kumbh cities.", "Centred on Shipra river snan and Mahakaleshwar Jyotirlinga.", "Useful for combining Ujjain with Omkareshwar, Maheshwar and Indore."],
    mythologyStories: [kumbhOrigin, { title: "Simhastha tradition", summary: "Ujjain Kumbh is popularly known as Simhastha and is associated in tradition with the Simha/Jupiter cycle, explained simply for travellers as a sacred timing tradition." }],
    historicalTimeline: [
      { period: "Traditional belief", title: "Kumbh origin", description: "Kumbh is connected with the Amrit Kalash story and sacred rivers." },
      { period: "2016", title: "Previous Ujjain Simhastha", description: "A major gathering around Shipra ghats, Mahakal area and temporary infrastructure." },
      { period: "2028", title: "Next major focus", description: "Dates and snan schedules remain tentative until official confirmation." },
    ],
    lastKumbhStats: { previousEventYear: "2016", estimatedPilgrims: "Very large gathering; exact figures vary by source", duration: "Festival period around Shipra river and Ujjain city", infrastructureNotes: "Temporary infrastructure, sanitation, medical support, traffic and ghat crowd management were critical.", crowdNotes: "Snan days need separate planning. Mahakal darshan and ghat visit should not be planned casually on peak days.", sourceNote: "Visitor estimates vary by source. Verify official figures before final publication. Verify current official dates, bathing dates, traffic rules and accommodation arrangements before publishing final content.", confidenceLevel: "editorial_estimate" },
    famousNamesAndInstitutions: [
      { name: "Mahakaleshwar Jyotirlinga", role: "Main temple", relevance: "Spiritual centre of Ujjain travel." },
      { name: "Akhara processions", role: "Kumbh tradition", relevance: "Important part of Simhastha camps and snan-day atmosphere." },
      { name: "Ram Ghat", role: "Sacred ghat", relevance: "One of the best-known Shipra ghats." },
    ],
    keyPlaces: [
      { name: "Mahakaleshwar Jyotirlinga", type: "temple", importance: "Main Jyotirlinga and central Ujjain pilgrimage anchor.", travellerTip: "Verify official darshan rules and avoid peak snan-day overload.", bestTimeToVisit: "Early morning, official rules permitting", seniorCitizenSuitability: "moderate", suggestedDuration: "2–4 hours", nearbyPlaces: ["Mahakal Lok", "Harsiddhi Temple"], tags: ["must_visit", "jyotirlinga", "family_friendly"] },
      { name: "Ram Ghat", type: "ghat", importance: "Important Shipra river ghat.", travellerTip: "Keep ghat visits separate from intense darshan days.", bestTimeToVisit: "Morning/evening", seniorCitizenSuitability: "moderate", suggestedDuration: "1–2 hours", nearbyPlaces: ["Shipra Ghats"], tags: ["must_visit", "near_main_kumbh_area"] },
      { name: "Shipra River Ghats", type: "river", importance: "Sacred riverfront for Simhastha snan.", travellerTip: "Use official entry and exit routes when published.", bestTimeToVisit: "Morning", seniorCitizenSuitability: "moderate", suggestedDuration: "1–2 hours", nearbyPlaces: ["Ram Ghat"], tags: ["near_main_kumbh_area"] },
      { name: "Kaal Bhairav Temple", type: "temple", importance: "Important Ujjain temple circuit stop.", travellerTip: "Good add-on outside peak hours.", bestTimeToVisit: "Morning/evening", seniorCitizenSuitability: "moderate", suggestedDuration: "1 hour", nearbyPlaces: ["Mangalnath"], tags: ["family_friendly"] },
      { name: "Harsiddhi Temple", type: "temple", importance: "Major Shakti temple near Mahakal area.", travellerTip: "Combine with Mahakal area only if crowds are manageable.", bestTimeToVisit: "Evening", seniorCitizenSuitability: "easy", suggestedDuration: "45 minutes", nearbyPlaces: ["Mahakaleshwar"], tags: ["near_main_kumbh_area", "family_friendly"] },
      { name: "Mangalnath Temple", type: "temple", importance: "Known for spiritual and astrological significance.", travellerTip: "Use local transport and avoid too many temples in one day.", bestTimeToVisit: "Morning", seniorCitizenSuitability: "moderate", suggestedDuration: "1 hour", nearbyPlaces: ["Kaal Bhairav"], tags: ["family_friendly"] },
      { name: "Sandipani Ashram", type: "temple", importance: "Traditional learning and Krishna-linked site.", travellerTip: "Good family-friendly calmer stop.", bestTimeToVisit: "Daytime", seniorCitizenSuitability: "easy", suggestedDuration: "1 hour", nearbyPlaces: ["Mangalnath"], tags: ["family_friendly", "senior_friendly"] },
      { name: "Omkareshwar", type: "nearby_destination", importance: "Jyotirlinga on the Narmada, often paired with Ujjain.", travellerTip: "Plan as a separate full day or overnight.", bestTimeToVisit: "October to March", seniorCitizenSuitability: "moderate", suggestedDuration: "1 day", nearbyPlaces: ["Maheshwar"], tags: ["nearby_add_on", "jyotirlinga"] },
      { name: "Maheshwar", type: "nearby_destination", importance: "Narmada ghats and heritage add-on.", travellerTip: "Good with Omkareshwar/Mandu if you have extra days.", bestTimeToVisit: "October to March", seniorCitizenSuitability: "easy", suggestedDuration: "Half to full day", nearbyPlaces: ["Omkareshwar"], tags: ["nearby_add_on", "family_friendly"] },
      { name: "Indore stay areas", type: "service_area", importance: "Practical airport and hotel hub.", travellerTip: "Stay in Indore for flight access and broader hotel choice.", bestTimeToVisit: "Stay base", seniorCitizenSuitability: "easy", suggestedDuration: "Base area", nearbyPlaces: ["Ujjain"], tags: ["senior_friendly", "family_friendly"] },
    ],
    usefulServices: ["Mahakal darshan planning", "Snan day crowd planning", "Local transport", "Medical support", "Police/helpdesk", "Drinking water", "Toilets", "Senior citizen assistance", "Package support"].map((title, index) => ({ title, description: `${title} information should be verified and updated as official Ujjain Simhastha arrangements are announced.`, priority: index + 1 })),
    travellerWarnings: ["Ujjain and Indore should be planned together for stay and flight arrival.", "Mahakal darshan and Shipra snan should be planned separately on peak days.", "Omkareshwar and Maheshwar are useful add-ons but need extra days."],
    seniorCitizenTips: ["Prefer Ujjain for short darshan-focused trips and Indore for hotel comfort.", "Do not combine long transfer, Mahakal darshan and Shipra snan in one packed day.", "Keep medicines, water and vehicle access plans ready."],
    familyTips: ["Set a meeting point near hotel and temple zone.", "Avoid peak heat and late-night transfers with children.", "Keep snacks, water and ID copies offline."],
    seoKeywords: ["Ujjain Kumbh 2028", "Ujjain Simhastha", "Mahakaleshwar Kumbh", "Shipra snan", "Ram Ghat Ujjain"],
  },
];

export function getKumbhGuide(slug: string) {
  return kumbhGuides.find((guide) => guide.slug === slug);
}
