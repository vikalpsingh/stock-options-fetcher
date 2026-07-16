import { getTravelProvider } from "@/src/data/travelProviders";
import { buildCampaignLabel, envOrDefault } from "./campaign";
import { assertNoUndefinedUrl, TravelValidationError, validateCitySlug, validatePassengers, validateTravelDate } from "./validation";

export type FlightProviderId = "easemytrip_flights" | "yatra_flights";

export function buildFlightUrl(params: {
  providerId?: FlightProviderId;
  fromCitySlug: string;
  toCitySlug: string;
  departureDate: string;
  returnDate?: string;
  adults?: number;
  children?: number;
  tripType?: "oneway" | "roundtrip";
  campaign?: string;
  sourcePage?: string;
}) {
  const providerId = params.providerId || "easemytrip_flights";
  return providerId === "yatra_flights" ? buildYatraFlightUrl({ ...params, providerId }) : buildEaseMyTripFlightUrl({ ...params, providerId });
}

export function buildEaseMyTripFlightUrl(params: Parameters<typeof buildFlightUrl>[0] & { providerId: FlightProviderId }) {
  const { from, to, label, pax } = prepareFlight(params);
  const provider = getTravelProvider("easemytrip_flights")!;
  const url = new URL(provider.baseUrl);
  // TODO: Verify final EaseMyTrip deep-link format after affiliate approval.
  url.searchParams.set("utm_source", label);
  url.searchParams.set("from", from.flightAirportCode!);
  url.searchParams.set("to", to.flightAirportCode!);
  url.searchParams.set("date", params.departureDate);
  url.searchParams.set("adults", String(pax.adults));
  if (process.env.EASEMYTRIP_AFFILIATE_ID) url.searchParams.set("affid", process.env.EASEMYTRIP_AFFILIATE_ID);
  return assertNoUndefinedUrl(url.toString());
}

export function buildYatraFlightUrl(params: Parameters<typeof buildFlightUrl>[0] & { providerId: FlightProviderId }) {
  const { from, to, label, pax } = prepareFlight(params);
  const provider = getTravelProvider("yatra_flights")!;
  const url = new URL(provider.baseUrl);
  // TODO: Verify final Yatra deep-link format after affiliate approval.
  url.searchParams.set("utm_source", label);
  url.searchParams.set("from", from.flightAirportCode!);
  url.searchParams.set("to", to.flightAirportCode!);
  url.searchParams.set("departureDate", params.departureDate);
  url.searchParams.set("adults", String(pax.adults));
  if (process.env.YATRA_AFFILIATE_ID) url.searchParams.set("affiliate_id", process.env.YATRA_AFFILIATE_ID);
  return assertNoUndefinedUrl(url.toString());
}

function prepareFlight(params: Parameters<typeof buildFlightUrl>[0] & { providerId: FlightProviderId }) {
  const from = validateCitySlug(params.fromCitySlug);
  const to = validateCitySlug(params.toCitySlug);
  if (!from.flightAirportCode || !to.flightAirportCode) throw new TravelValidationError("airport-code-missing");
  validateTravelDate(params.departureDate, "invalid-departure-date");
  if (params.tripType === "roundtrip") {
    const ret = validateTravelDate(params.returnDate, "invalid-return-date");
    if (ret <= params.departureDate) throw new TravelValidationError("return-before-departure");
  }
  const pax = validatePassengers(params.adults, params.children);
  const provider = getTravelProvider(params.providerId)!;
  const label = buildCampaignLabel({ providerId: provider.id, mode: "flight", city: `${from.slug}-to-${to.slug}`, campaign: params.campaign, sourcePage: params.sourcePage, prefix: envOrDefault(provider.campaignPrefixEnvKey, provider.defaultCampaignPrefix) });
  return { from, to, pax, label };
}
