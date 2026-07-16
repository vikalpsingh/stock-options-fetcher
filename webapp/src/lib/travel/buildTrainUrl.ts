import { getTravelProvider } from "@/src/data/travelProviders";
import { buildCampaignLabel, envOrDefault } from "./campaign";
import { assertNoUndefinedUrl, TravelValidationError, validateCitySlug, validateTravelDate } from "./validation";

export type TrainProviderId = "irctc_tourism" | "irctc_official_reference" | "redbus_train" | "easemytrip_train";

export function buildTrainUrl(params: {
  providerId?: TrainProviderId;
  fromCitySlug: string;
  toCitySlug: string;
  journeyDate: string;
  campaign?: string;
  sourcePage?: string;
}) {
  const providerId = params.providerId || "irctc_tourism";
  const provider = getTravelProvider(providerId);
  if (!provider) throw new TravelValidationError("invalid-provider");
  const from = validateCitySlug(params.fromCitySlug);
  const to = validateCitySlug(params.toCitySlug);
  validateTravelDate(params.journeyDate, "invalid-journey-date");
  if (!from.railwayStationCodes.length || !to.railwayStationCodes.length) throw new TravelValidationError("station-code-missing");
  const label = buildCampaignLabel({ providerId, mode: "train", city: `${from.slug}-to-${to.slug}`, campaign: params.campaign, sourcePage: params.sourcePage, prefix: envOrDefault(provider.campaignPrefixEnvKey, provider.defaultCampaignPrefix) });
  const url = new URL(provider.baseUrl);
  // Phase 1: redirect/reference only. Do not collect passenger name, age, ID proof, or payment details.
  // Future IRCTC PSP/API work requires legal approval, partner agreement, payment, refund, support and audit workflows.
  if (providerId !== "irctc_official_reference") {
    url.searchParams.set("utm_source", label);
    url.searchParams.set("from", from.railwayStationCodes[0]);
    url.searchParams.set("to", to.railwayStationCodes[0]);
    url.searchParams.set("date", params.journeyDate);
  }
  return assertNoUndefinedUrl(url.toString());
}
