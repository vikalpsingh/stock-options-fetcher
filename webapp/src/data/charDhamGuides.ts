export type CharDhamSite = {
  slug: string;
  templeName: string;
  deity: string;
  state: string;
  region: string;
  riverOrSacredWater?: string;
  altitudeLabel?: string;
  routeOrder: number;
  baseTown: string;
  nearestAirport: string;
  nearestRailwayStation: string;
  usualOpeningSeason: string;
  difficulty: "easy" | "moderate" | "difficult";
  seniorCitizenSuitability: "easy" | "moderate" | "challenging";
  registrationRequired: boolean;
  helicopterAvailable: boolean;
  ponyPalkiAvailable?: boolean;
  shortDescription: string;
  spiritualImportance: string[];
  mythologyStories: { title: string; summary: string }[];
  historicalNotes: { title: string; description: string }[];
  famousNamesAndTraditions: { name: string; role: string; relevance: string }[];
  usefulPlaces: { name: string; type: "temple" | "base_town" | "river" | "kund" | "viewpoint" | "service_area" | "nearby_destination"; importance: string; travellerTip: string; seniorCitizenNote?: string }[];
  usefulServices: string[];
  travellerWarnings: string[];
  seniorCitizenTips: string[];
  familyTips: string[];
  seoKeywords: string[];
};

export const charDhamGlobalNote = "Registration, opening dates, route conditions, weather alerts, helicopter booking and health advisories must be verified from official Uttarakhand portals before travel.";

const commonServices = ["Official registration", "Vehicle registration", "Health advisory", "Hotels and dharamshala", "Local taxi/shared jeep", "Medical and emergency support", "Food and drinking water", "Toilets and sanitation", "Package quote"];

export const charDhamGuides: CharDhamSite[] = [
  {
    slug: "yamunotri",
    templeName: "Yamunotri Temple",
    deity: "Goddess Yamuna",
    state: "Uttarakhand",
    region: "Uttarakhand Garhwal",
    riverOrSacredWater: "Yamuna river",
    altitudeLabel: "High Himalayan temple area",
    routeOrder: 1,
    baseTown: "Barkot / Janki Chatti",
    nearestAirport: "Dehradun",
    nearestRailwayStation: "Dehradun / Rishikesh",
    usualOpeningSeason: "Usually summer to autumn, subject to official temple schedule",
    difficulty: "difficult",
    seniorCitizenSuitability: "challenging",
    registrationRequired: true,
    helicopterAvailable: false,
    ponyPalkiAvailable: true,
    shortDescription: "Yamunotri is the usual first stop of Uttarakhand Char Dham Yatra and is associated with Maa Yamuna.",
    spiritualImportance: ["Source-region pilgrimage of Yamuna Maa.", "Traditional beginning of Char Dham route order.", "Darshan is associated with purification and family wellbeing in traditional belief."],
    mythologyStories: [{ title: "Yamuna, Surya and Yama", summary: "Traditional belief connects Yamuna Maa with Surya and Yama. Yamuna darshan is seen as spiritually purifying and protective." }],
    historicalNotes: [{ title: "Mountain yatra tradition", description: "Yamunotri has long been part of the Himalayan pilgrimage route where travellers combine devotion with careful hill travel." }],
    famousNamesAndTraditions: [{ name: "Yamuna Maa", role: "Main deity", relevance: "Central sacred presence of Yamunotri." }],
    usefulPlaces: [
      place("Janki Chatti", "base_town", "Main last-mile base before Yamunotri trek.", "Confirm pony/palki and route conditions locally.", "Challenging for elders without assistance."),
      place("Yamunotri Temple", "temple", "Main temple of Goddess Yamuna.", "Start early and keep weather buffer.", "Use pony/palki if walking is difficult."),
      place("Surya Kund", "kund", "Sacred hot spring near temple.", "Follow local safety instructions near hot water."),
      place("Divya Shila", "temple", "Traditional worship point near temple.", "Keep visit short if crowds are heavy."),
      place("Barkot", "base_town", "Practical stay base before Yamunotri.", "Good rest point for families."),
    ],
    usefulServices: commonServices,
    travellerWarnings: ["Trekking is involved from the Janki Chatti area.", "Weather and route conditions can change quickly.", "Pony/palki availability is subject to local arrangements."],
    seniorCitizenTips: ["Do not rush Yamunotri on the first day.", "Consider pony/palki support.", "Keep rain protection, medicines and warm layers handy."],
    familyTips: ["Start early.", "Keep children close on narrow paths.", "Carry snacks, water and offline hotel details."],
    seoKeywords: ["Yamunotri Yatra", "Char Dham Yamunotri", "Janki Chatti Yamunotri"],
  },
  {
    slug: "gangotri",
    templeName: "Gangotri Temple",
    deity: "Goddess Ganga",
    state: "Uttarakhand",
    region: "Uttarakhand Garhwal",
    riverOrSacredWater: "Bhagirathi / Ganga",
    altitudeLabel: "High Himalayan road-access temple area",
    routeOrder: 2,
    baseTown: "Uttarkashi",
    nearestAirport: "Dehradun",
    nearestRailwayStation: "Rishikesh / Dehradun",
    usualOpeningSeason: "Usually summer to autumn, subject to official temple schedule",
    difficulty: "moderate",
    seniorCitizenSuitability: "moderate",
    registrationRequired: true,
    helicopterAvailable: false,
    shortDescription: "Gangotri is the Char Dham temple associated with Maa Ganga and the Bhagirathi river.",
    spiritualImportance: ["Sacred Ganga origin-region pilgrimage.", "Important stop after Yamunotri in the usual Char Dham route.", "Uttarkashi and Harsil make it useful for slower family planning."],
    mythologyStories: [{ title: "Bhagirath and the descent of Ganga", summary: "Traditional belief says King Bhagirath performed tapasya so Maa Ganga descended for the liberation of his ancestors." }],
    historicalNotes: [{ title: "Ganga devotion", description: "Gangotri is central to Himalayan Ganga worship and is visited by pilgrims seeking darshan of Maa Ganga." }],
    famousNamesAndTraditions: [{ name: "Bhagirath", role: "Traditional figure", relevance: "Associated with the descent of Ganga story." }],
    usefulPlaces: [place("Gangotri Temple", "temple", "Main temple of Maa Ganga.", "Avoid peak crowd hours."), place("Bhagirathi River", "river", "Sacred river at Gangotri.", "Stay within safe river areas."), place("Uttarkashi", "base_town", "Practical base town.", "Good for rest and supplies."), place("Harsil", "nearby_destination", "Scenic halt near Gangotri.", "Useful for slower itineraries."), place("Gaumukh trek", "viewpoint", "Advanced trek note only.", "Only for fit travellers with permits and guidance.")],
    usefulServices: commonServices,
    travellerWarnings: ["Altitude and cold can affect elders.", "Gaumukh is not a casual family walk.", "Road movement depends on mountain conditions."],
    seniorCitizenTips: ["Use Uttarkashi/Harsil as rest bases.", "Avoid long back-to-back drives.", "Carry warm clothing."],
    familyTips: ["Keep buffer in Uttarkashi.", "Avoid riverside risk-taking.", "Plan simple food before long drives."],
    seoKeywords: ["Gangotri Yatra", "Char Dham Gangotri", "Bhagirathi Ganga"],
  },
  {
    slug: "kedarnath",
    templeName: "Kedarnath Temple",
    deity: "Lord Shiva",
    state: "Uttarakhand",
    region: "Uttarakhand Garhwal",
    riverOrSacredWater: "Mandakini region",
    altitudeLabel: "High-altitude Himalayan temple",
    routeOrder: 3,
    baseTown: "Sonprayag / Gaurikund",
    nearestAirport: "Dehradun",
    nearestRailwayStation: "Rishikesh / Haridwar",
    usualOpeningSeason: "Temple opening season, subject to official schedule and weather",
    difficulty: "difficult",
    seniorCitizenSuitability: "challenging",
    registrationRequired: true,
    helicopterAvailable: true,
    ponyPalkiAvailable: true,
    shortDescription: "Kedarnath is both a Char Dham temple and a Jyotirlinga, requiring serious health and route planning.",
    spiritualImportance: ["One of the most revered Shiva temples.", "Part of both Char Dham and 12 Jyotirlinga traditions.", "Connected with Pandava and Panch Kedar beliefs."],
    mythologyStories: [{ title: "Pandavas and Lord Shiva", summary: "Traditional belief links Kedarnath with the Pandavas seeking Lord Shiva after the Mahabharata war and the wider Panch Kedar tradition." }],
    historicalNotes: [{ title: "Himalayan Shiva pilgrimage", description: "Kedarnath is a deeply revered high-altitude pilgrimage where devotion must be balanced with health planning." }],
    famousNamesAndTraditions: [{ name: "Pandavas", role: "Traditional figures", relevance: "Associated with the Kedarnath and Panch Kedar story." }],
    usefulPlaces: [place("Kedarnath Temple", "temple", "Main Shiva temple and Jyotirlinga.", "Verify darshan, route and weather status."), place("Gaurikund", "base_town", "Trek base.", "Plan last-mile carefully."), place("Sonprayag", "service_area", "Transport control and transfer area.", "Expect queues during peak season."), place("Guptkashi", "base_town", "Practical stay halt.", "Useful for rest before Kedarnath."), place("Triyuginarayan", "nearby_destination", "Important nearby temple.", "Add only with enough buffer.")],
    usefulServices: commonServices,
    travellerWarnings: ["High altitude.", "Weather changes.", "Long trek or helicopter dependency.", "Medical readiness is essential."],
    seniorCitizenTips: ["Get medical advice before travel.", "Use buffer days.", "Do not rely only on same-day helicopter plans."],
    familyTips: ["Keep warm layers and rain protection.", "Avoid splitting groups without meeting points.", "Do not overpack the Kedarnath day."],
    seoKeywords: ["Kedarnath Yatra", "Kedarnath Char Dham", "Kedarnath Jyotirlinga"],
  },
  {
    slug: "badrinath",
    templeName: "Badrinath Temple",
    deity: "Lord Vishnu / Badri Vishal",
    state: "Uttarakhand",
    region: "Uttarakhand Garhwal",
    riverOrSacredWater: "Alaknanda River",
    altitudeLabel: "High Himalayan road-access temple area",
    routeOrder: 4,
    baseTown: "Joshimath / Badrinath",
    nearestAirport: "Dehradun",
    nearestRailwayStation: "Rishikesh / Haridwar",
    usualOpeningSeason: "Usually summer to autumn, subject to official temple schedule",
    difficulty: "moderate",
    seniorCitizenSuitability: "moderate",
    registrationRequired: true,
    helicopterAvailable: false,
    shortDescription: "Badrinath is the Vishnu pilgrimage that usually completes the Uttarakhand Char Dham sequence.",
    spiritualImportance: ["Major Lord Vishnu pilgrimage.", "Usual final stop of Uttarakhand Char Dham.", "Associated with Nar-Narayan and Adi Shankaracharya tradition."],
    mythologyStories: [{ title: "Lord Vishnu at Badrinath", summary: "Traditional belief associates Badrinath with Lord Vishnu's meditation, Nar-Narayan and the sacred Alaknanda region." }],
    historicalNotes: [{ title: "Adi Shankaracharya tradition", description: "Badrinath is associated in pilgrimage tradition with Adi Shankaracharya's role in reviving sacred routes." }],
    famousNamesAndTraditions: [{ name: "Adi Shankaracharya", role: "Pilgrimage tradition", relevance: "Associated with revival of major Hindu pilgrimage traditions." }],
    usefulPlaces: [place("Badrinath Temple", "temple", "Main Badri Vishal temple.", "Verify opening schedule and darshan rules."), place("Tapt Kund", "kund", "Sacred hot water kund near temple.", "Follow crowd and safety instructions."), place("Mana Village", "nearby_destination", "Last village area and popular add-on.", "Add only with weather and time buffer."), place("Alaknanda River", "river", "Sacred river setting.", "Avoid unsafe river edges."), place("Joshimath", "base_town", "Important base town.", "Good rest and acclimatisation halt.")],
    usefulServices: commonServices,
    travellerWarnings: ["Road and weather conditions can change.", "Altitude can still affect elders.", "Avoid night hill travel."],
    seniorCitizenTips: ["Keep rest time in Joshimath/Badrinath.", "Avoid rushing after Kedarnath.", "Carry warm layers."],
    familyTips: ["Plan Mana only if everyone has energy.", "Keep food and water ready before long drives.", "Check hotel access and parking."],
    seoKeywords: ["Badrinath Yatra", "Char Dham Badrinath", "Badri Vishal"],
  },
];

function place(name: CharDhamSite["usefulPlaces"][number]["name"], type: CharDhamSite["usefulPlaces"][number]["type"], importance: string, travellerTip: string, seniorCitizenNote?: string) {
  return { name, type, importance, travellerTip, seniorCitizenNote };
}

export function getCharDhamGuide(slug: string) {
  return charDhamGuides.find((site) => site.slug === slug);
}
