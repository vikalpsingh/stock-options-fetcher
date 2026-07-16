import type { TravelMode } from "@/src/data/travelProviders";
import { sanitizeCampaignLabel } from "./validation";

export function buildCampaignLabel({
  providerId,
  mode,
  city,
  campaign,
  sourcePage,
  prefix,
}: {
  providerId: string;
  mode: TravelMode;
  city?: string;
  campaign?: string;
  sourcePage?: string;
  prefix?: string;
}) {
  return sanitizeCampaignLabel([prefix || "indiankumbh", campaign || providerId, mode, city, sourcePage].filter(Boolean).join("-")).slice(0, 120);
}

export function envOrDefault(key?: string, fallback = "indiankumbh") {
  return key ? process.env[key] || fallback : fallback;
}
