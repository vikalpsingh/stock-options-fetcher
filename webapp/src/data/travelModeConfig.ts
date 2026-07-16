import type { TravelMode } from "./travelProviders";

export const travelModeConfig: Record<TravelMode, { primary: string; fallbacks: string[] }> = {
  bus: { primary: "redbus", fallbacks: ["easemytrip_bus"] },
  hotel: { primary: "booking", fallbacks: ["yatra_hotels"] },
  flight: { primary: "easemytrip_flights", fallbacks: ["yatra_flights"] },
  train: { primary: "irctc_tourism", fallbacks: ["irctc_official_reference", "redbus_train", "easemytrip_train"] },
  package: { primary: "package_lead_form", fallbacks: [] },
};

export function getDefaultProviderForMode(mode: TravelMode) {
  return travelModeConfig[mode].primary;
}
