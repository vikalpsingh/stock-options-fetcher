import { getTravelProvider } from "@/src/data/travelProviders";
import { isVerifiedProviderId } from "@/src/data/travelCities";
import { buildCampaignLabel, envOrDefault } from "./campaign";
import { assertNoUndefinedUrl, formatRedbusDate, TravelValidationError, validateCitySlug, validateTravelDate } from "./validation";

export function buildRedbusUrl(params: {
  fromCitySlug: string;
  toCitySlug: string;
  date: string;
  campaign?: string;
  sourcePage?: string;
}) {
  const provider = getTravelProvider("redbus")!;
  const from = validateCitySlug(params.fromCitySlug);
  const to = validateCitySlug(params.toCitySlug);
  validateTravelDate(params.date);
  if (!isVerifiedProviderId(from.redbusCityId) || !isVerifiedProviderId(to.redbusCityId)) {
    throw new TravelValidationError("redbus-city-id-unverified");
  }
  const label = buildCampaignLabel({ providerId: provider.id, mode: "bus", city: `${from.slug}-to-${to.slug}`, campaign: params.campaign, sourcePage: params.sourcePage, prefix: envOrDefault(provider.campaignPrefixEnvKey, provider.defaultCampaignPrefix) });
  const url = new URL(provider.baseUrl);
  url.searchParams.set("fromCityId", from.redbusCityId!);
  url.searchParams.set("fromCityName", from.cityName);
  url.searchParams.set("toCityId", to.redbusCityId!);
  url.searchParams.set("toCityName", to.cityName);
  url.searchParams.set("onward", formatRedbusDate(params.date));
  url.searchParams.set("doj", formatRedbusDate(params.date));
  url.searchParams.set("ref", process.env.REDBUS_AFFILIATE_ID || label);
  return assertNoUndefinedUrl(url.toString());
}
