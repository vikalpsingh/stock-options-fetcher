import { getTravelCityBySlug } from "@/src/data/travelCities";

export class TravelValidationError extends Error {
  safeReason: string;
  constructor(safeReason: string) {
    super(safeReason);
    this.name = "TravelValidationError";
    this.safeReason = safeReason;
  }
}

export function validateCitySlug(slug?: string) {
  const city = getTravelCityBySlug(slug);
  if (!city) throw new TravelValidationError("invalid-city");
  return city;
}

export function validateTravelDate(date?: string, reason = "invalid-date") {
  if (!date || !isIsoDate(date)) throw new TravelValidationError(reason);
  return date;
}

export function validateDateRange(checkin?: string, checkout?: string) {
  const start = validateTravelDate(checkin, "invalid-checkin");
  const end = validateTravelDate(checkout, "invalid-checkout");
  return { checkin: start, checkout: end > start ? end : addDays(start, 1) };
}

export function validatePassengers(adults?: number, children?: number) {
  const safeAdults = Number.isInteger(adults) && adults! >= 1 ? adults! : 1;
  const safeChildren = Number.isInteger(children) && children! >= 0 ? children! : 0;
  return { adults: safeAdults, children: safeChildren };
}

export function sanitizeCampaignLabel(label?: string) {
  return (label || "travel")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 90) || "travel";
}

export function assertNoUndefinedUrl(url: string) {
  if (/(undefined|null|NaN|\[object Object\]|chal_t|force_referer|destinationCity|travellersCount)/i.test(url)) {
    throw new TravelValidationError("unsafe-url");
  }
  if (/=(?:&|$)/.test(new URL(url, "https://indiankumbh.com").search)) {
    throw new TravelValidationError("empty-url-param");
  }
  return url;
}

export function addDays(date: string, days: number) {
  const [year, month, day] = date.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return parsed.toISOString().slice(0, 10);
}

export function formatRedbusDate(date: string) {
  validateTravelDate(date);
  const [, year, month, day] = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)!;
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${day}-${monthNames[Number(month) - 1]}-${year}`;
}

function isIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}
