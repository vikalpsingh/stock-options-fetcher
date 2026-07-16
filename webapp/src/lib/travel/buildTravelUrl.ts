import type { TravelMode } from "@/src/data/travelProviders";
import { getTravelProvider } from "@/src/data/travelProviders";
import { getDefaultProviderForMode } from "@/src/data/travelModeConfig";
import { buildCampaignLabel } from "./campaign";
import { buildBookingUrl } from "./buildBookingUrl";
import { buildFlightUrl, type FlightProviderId } from "./buildFlightUrl";
import { buildRedbusUrl } from "./buildRedbusUrl";
import { buildTrainUrl, type TrainProviderId } from "./buildTrainUrl";
import { assertNoUndefinedUrl, TravelValidationError } from "./validation";

export type BuildTravelUrlParams = {
  mode: Exclude<TravelMode, "package">;
  providerId?: string;
  fromCitySlug?: string;
  toCitySlug?: string;
  citySlug?: string;
  date?: string;
  checkin?: string;
  checkout?: string;
  departureDate?: string;
  returnDate?: string;
  adults?: number;
  children?: number;
  rooms?: number;
  tripType?: "oneway" | "roundtrip";
  campaign?: string;
  sourcePage?: string;
};

export function buildTravelUrl(params: BuildTravelUrlParams) {
  const providerId = params.providerId || getDefaultProviderForMode(params.mode);
  const provider = getTravelProvider(providerId);
  if (!provider || provider.mode !== params.mode) throw new TravelValidationError("invalid-provider");
  let url: string;
  if (params.mode === "bus") {
    url = buildRedbusUrl({ fromCitySlug: required(params.fromCitySlug, "missing-from"), toCitySlug: required(params.toCitySlug, "missing-to"), date: required(params.date, "missing-date"), campaign: params.campaign, sourcePage: params.sourcePage });
  } else if (params.mode === "hotel") {
    url = buildBookingUrl({ citySlug: required(params.citySlug, "missing-city"), checkin: required(params.checkin, "missing-checkin"), checkout: required(params.checkout, "missing-checkout"), adults: params.adults, children: params.children, rooms: params.rooms, campaign: params.campaign, sourcePage: params.sourcePage });
  } else if (params.mode === "flight") {
    url = buildFlightUrl({ providerId: providerId as FlightProviderId, fromCitySlug: required(params.fromCitySlug, "missing-from"), toCitySlug: required(params.toCitySlug, "missing-to"), departureDate: required(params.departureDate, "missing-departure-date"), returnDate: params.returnDate, adults: params.adults, children: params.children, tripType: params.tripType, campaign: params.campaign, sourcePage: params.sourcePage });
  } else {
    url = buildTrainUrl({ providerId: providerId as TrainProviderId, fromCitySlug: required(params.fromCitySlug, "missing-from"), toCitySlug: required(params.toCitySlug, "missing-to"), journeyDate: required(params.date, "missing-date"), campaign: params.campaign, sourcePage: params.sourcePage });
  }
  const campaignLabel = buildCampaignLabel({ providerId, mode: params.mode, city: params.citySlug || `${params.fromCitySlug || ""}-to-${params.toCitySlug || ""}`, campaign: params.campaign, sourcePage: params.sourcePage });
  return { url: assertNoUndefinedUrl(url), providerId, mode: params.mode, campaignLabel };
}

function required(value: string | undefined, reason: string) {
  if (!value) throw new TravelValidationError(reason);
  return value;
}

/*
Examples:
- Bus Bengaluru to Ujjain:
  buildTravelUrl({ mode: "bus", fromCitySlug: "bengaluru", toCitySlug: "ujjain", date: "2026-07-13" })
- Hotel Indore stay:
  buildTravelUrl({ mode: "hotel", citySlug: "indore", checkin: "2026-07-15", checkout: "2026-07-16", adults: 2 })
- Flight Bengaluru to Indore:
  buildTravelUrl({ mode: "flight", fromCitySlug: "bengaluru", toCitySlug: "indore", departureDate: "2026-07-13" })
- Train Mumbai to Ujjain:
  buildTravelUrl({ mode: "train", fromCitySlug: "mumbai", toCitySlug: "ujjain", date: "2026-07-13" })
*/
