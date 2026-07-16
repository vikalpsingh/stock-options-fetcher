import { getTravelProvider } from "@/src/data/travelProviders";
import { buildCampaignLabel, envOrDefault } from "./campaign";
import { assertNoUndefinedUrl, validateCitySlug, validateDateRange, validatePassengers } from "./validation";

export function buildBookingUrl(params: {
  citySlug: string;
  checkin: string;
  checkout: string;
  adults?: number;
  children?: number;
  rooms?: number;
  campaign?: string;
  sourcePage?: string;
}) {
  const provider = getTravelProvider("booking")!;
  const city = validateCitySlug(params.citySlug);
  if (!city.bookingSearchText) throw new Error("booking-search-text-missing");
  const dates = validateDateRange(params.checkin, params.checkout);
  const pax = validatePassengers(params.adults ?? 2, params.children ?? 0);
  const rooms = Number.isInteger(params.rooms) && params.rooms! >= 1 ? params.rooms! : 1;
  const label = buildCampaignLabel({ providerId: provider.id, mode: "hotel", city: city.slug, campaign: params.campaign, sourcePage: params.sourcePage, prefix: envOrDefault(provider.campaignPrefixEnvKey, provider.defaultCampaignPrefix) });
  const url = new URL(provider.baseUrl);
  url.searchParams.set("ss", city.bookingSearchText);
  url.searchParams.set("checkin", dates.checkin);
  url.searchParams.set("checkout", dates.checkout);
  url.searchParams.set("group_adults", String(pax.adults));
  url.searchParams.set("group_children", String(pax.children));
  url.searchParams.set("no_rooms", String(rooms));
  url.searchParams.set("label", label);
  url.searchParams.set("selected_currency", "INR");
  url.searchParams.set("lang", "en-gb");
  if (process.env.BOOKING_AFFILIATE_ID) url.searchParams.set("aid", process.env.BOOKING_AFFILIATE_ID);
  return assertNoUndefinedUrl(url.toString());
}
