import type { TripPlannerInput, TripRecommendation } from "./trip-planner";

export type AffiliateLinkConfig = {
  travelBaseUrl?: string;
  hotelBaseUrl?: string;
};

export type AffiliateLinks = {
  travelUrl: string;
  hotelUrl: string;
  travelPartnerConfigured: boolean;
  hotelPartnerConfigured: boolean;
};

const travelFallback = "https://www.redbus.in/search";
const hotelFallback = "https://www.booking.com/searchresults.html";

export function generateAffiliateLinks(
  input: TripPlannerInput,
  recommendation: TripRecommendation,
  config: AffiliateLinkConfig,
): AffiliateLinks {
  return {
    travelUrl: withQuery(config.travelBaseUrl || travelFallback, {
      fromCity: input.fromCity,
      destinationCity: recommendation.destinationCity,
      travelDate: input.travelDate,
      returnDate: input.returnDate,
      travellersCount: String(input.travellersCount),
      travelMode: input.travelMode,
    }),
    hotelUrl: withQuery(config.hotelBaseUrl || hotelFallback, {
      destinationCity: recommendation.stayCity,
      checkin: input.travelDate,
      checkout: input.returnDate,
      travellersCount: String(input.travellersCount),
      budget: input.budget,
    }),
    travelPartnerConfigured: Boolean(config.travelBaseUrl),
    hotelPartnerConfigured: Boolean(config.hotelBaseUrl),
  };
}

function withQuery(baseUrl: string, values: Record<string, string>) {
  try {
    const url = new URL(baseUrl);
    Object.entries(values).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
    });
    return url.toString();
  } catch {
    const separator = baseUrl.includes("?") ? "&" : "?";
    return `${baseUrl}${separator}${new URLSearchParams(values).toString()}`;
  }
}

