export const travelModes = ["bus", "train", "flight", "not_sure"] as const;
export const stayCities = ["Ujjain", "Indore", "Bhopal", "not_sure"] as const;
export const budgetLevels = ["budget", "standard", "premium"] as const;

export type TravelMode = (typeof travelModes)[number];
export type StayCityPreference = (typeof stayCities)[number];
export type BudgetLevel = (typeof budgetLevels)[number];
export type RecommendedStayCity = Exclude<StayCityPreference, "not_sure">;

export type TripPlannerInput = {
  fromCity: string;
  travelDate: string;
  returnDate: string;
  travellersCount: number;
  hasSeniorCitizens: boolean;
  travelMode: TravelMode;
  stayCityPreference: StayCityPreference;
  budget: BudgetLevel;
  needsDarshanHelp: boolean;
  needsLocalTransport: boolean;
};

export type TripRecommendation = {
  stayCity: RecommendedStayCity;
  stayReason: string;
  routeSuggestion: string;
  crowdPlanningNote: string;
  practicalActions: string[];
  destinationCity: string;
};

const longDistanceOrigins = ["delhi", "mumbai", "pune", "ahmedabad", "bengaluru", "bangalore", "kolkata", "chennai", "hyderabad"];

export function generateTripRecommendation(input: TripPlannerInput): TripRecommendation {
  const stayCity = recommendStayCity(input);
  const routeSuggestion = buildRouteSuggestion(input, stayCity);
  const practicalActions = [
    input.hasSeniorCitizens
      ? "Keep the arrival day light and confirm lift, vehicle access and walking distance directly with the hotel."
      : "Keep the arrival day flexible so a delayed train, bus or flight does not affect darshan.",
    input.needsDarshanHelp
      ? "Use only official Mahakal temple channels for darshan or Bhasma Aarti information; avoid unofficial agents."
      : "Check current Mahakal entry rules from official sources shortly before travel.",
    input.needsLocalTransport
      ? "Ask the stay property about current shuttle points, restricted zones and a reliable local driver before arrival."
      : "Save your hotel, railway station and family meeting point offline before entering crowded areas.",
  ];

  return {
    stayCity,
    stayReason: stayReasonFor(stayCity, input),
    routeSuggestion,
    crowdPlanningNote: crowdNoteFor(input),
    practicalActions,
    destinationCity: input.travelMode === "flight" ? "Indore" : stayCity,
  };
}

function recommendStayCity(input: TripPlannerInput): RecommendedStayCity {
  if (input.stayCityPreference !== "not_sure") return input.stayCityPreference;
  if (input.hasSeniorCitizens || input.needsDarshanHelp) return "Ujjain";
  if (input.travelMode === "flight" || input.budget === "premium") return "Indore";
  return "Ujjain";
}

function stayReasonFor(city: RecommendedStayCity, input: TripPlannerInput) {
  if (city === "Ujjain") {
    return input.hasSeniorCitizens
      ? "Ujjain reduces repeated road transfers and is usually the practical choice when senior citizens need a slower darshan day."
      : "Ujjain keeps Mahakal darshan and the main pilgrimage area closer, reducing daily transfer time.";
  }
  if (city === "Indore") {
    return input.travelMode === "flight"
      ? "Indore is the practical airport gateway and offers a wider hotel range; plan an early, buffered road transfer to Ujjain."
      : "Indore offers a wider choice of standard and premium hotels, food and onward transport.";
  }
  return "Bhopal is most useful when Ujjain is part of a wider Madhya Pradesh trip including Sanchi or Bhimbetka; it is not ideal for daily Mahakal travel.";
}

function buildRouteSuggestion(input: TripPlannerInput, stayCity: RecommendedStayCity) {
  const from = cleanCity(input.fromCity);
  if (input.travelMode === "flight") {
    return `Fly from ${from} to Indore, then use a pre-booked road transfer${stayCity === "Ujjain" ? " to Ujjain" : " to your Indore stay"}. Keep extra transfer time during Kumbh traffic controls.`;
  }
  if (input.travelMode === "train") {
    return stayCity === "Ujjain"
      ? `Search direct trains from ${from} to Ujjain Junction first. If availability is poor, compare Indore Junction and continue by road.`
      : `Search trains from ${from} to ${stayCity}. For Mahakal darshan, reserve a separate early road transfer to Ujjain.`;
  }
  if (input.travelMode === "bus") {
    return `Compare direct buses from ${from} to ${stayCity}. Choose a daytime arrival where possible and confirm the actual drop point before booking.`;
  }
  const isLongDistance = longDistanceOrigins.some((city) => from.toLowerCase().includes(city));
  return isLongDistance
    ? `Compare a train to Ujjain with a flight to Indore. For ${from}, the best choice will depend on confirmed schedules, total door-to-door time and cancellation terms.`
    : `Compare direct train and bus options from ${from} to Ujjain. Prefer the option with a reliable arrival time and fewer transfers.`;
}

function crowdNoteFor(input: TripPlannerInput) {
  const groupNote = input.travellersCount >= 5
    ? "For your group, choose one meeting point and keep a shared copy of hotel and emergency details."
    : "Keep hotel details, IDs and one family meeting point available offline.";
  const seniorNote = input.hasSeniorCitizens
    ? " Avoid peak heat, keep medicines and water accessible, and do not combine a long transfer with a demanding darshan plan."
    : " Leave a generous buffer between arrival, hotel check-in and darshan.";
  return `Official 2028 dates, bathing-day controls and traffic plans are still subject to confirmation. ${groupNote}${seniorNote}`;
}

function cleanCity(city: string) {
  return city.trim().replace(/\s+/g, " ");
}

