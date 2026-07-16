import { getHotelCityBySlug } from "@/src/data/hotelCities";

export type BookingBudget = "budget" | "standard" | "premium";

export type BuildBookingSearchUrlParams = {
  citySlug: string;
  checkin: string;
  checkout: string;
  adults?: number;
  rooms?: number;
  children?: number;
  budget?: BookingBudget;
  campaign?: string;
  sourcePage?: string;
};

export class BookingUrlValidationError extends Error {
  safeReason: string;

  constructor(safeReason: string) {
    super(safeReason);
    this.name = "BookingUrlValidationError";
    this.safeReason = safeReason;
  }
}

const bookingBaseUrl = "https://www.booking.com/searchresults.html";

export function buildBookingSearchUrl(params: BuildBookingSearchUrlParams): string {
  const city = getHotelCityBySlug(params.citySlug);
  if (!city) throw new BookingUrlValidationError("invalid-city");

  const checkin = normalizeDate(params.checkin, "invalid-checkin");
  const rawCheckout = normalizeDate(params.checkout, "invalid-checkout");
  const checkout = rawCheckout > checkin ? rawCheckout : addDays(checkin, city.defaultNights);
  const adults = positiveInt(params.adults, 2);
  const rooms = positiveInt(params.rooms, 1);
  const children = nonNegativeInt(params.children, 0);
  const budget = isBudget(params.budget) ? params.budget : "standard";
  const campaign = sanitizeLabelPart(params.campaign || "hotel-search");
  const sourcePage = sanitizeLabelPart(params.sourcePage || "indiankumbh");
  const label = ["indiankumbh", campaign, city.slug, budget, sourcePage].filter(Boolean).join("-");
  const affiliateId = process.env.BOOKING_AFFILIATE_ID || process.env.NEXT_PUBLIC_BOOKING_AFFILIATE_ID || "";
  const url = new URL(bookingBaseUrl);

  url.searchParams.set("ss", city.bookingSearchText);
  url.searchParams.set("checkin", checkin);
  url.searchParams.set("checkout", checkout);
  url.searchParams.set("group_adults", String(adults));
  url.searchParams.set("no_rooms", String(rooms));
  url.searchParams.set("group_children", String(children));
  url.searchParams.set("label", label);
  url.searchParams.set("selected_currency", "INR");
  url.searchParams.set("lang", "en-gb");
  if (affiliateId) url.searchParams.set("aid", affiliateId);

  const finalUrl = url.toString();
  if (/(undefined|null|chal_t|force_referer|destinationCity|travellersCount)/i.test(finalUrl)) {
    throw new BookingUrlValidationError("unsafe-booking-url");
  }

  return finalUrl;
}

export function getDefaultHotelDates(citySlug = "ujjain", now = new Date()) {
  const city = getHotelCityBySlug(citySlug) || getHotelCityBySlug("ujjain")!;
  const checkin = addDays(toIsoDate(now), 30);
  return { checkin, checkout: addDays(checkin, city.defaultNights) };
}

export function addDays(date: string, days: number) {
  const [year, month, day] = date.split("-").map(Number);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  utcDate.setUTCDate(utcDate.getUTCDate() + days);
  return utcDate.toISOString().slice(0, 10);
}

function normalizeDate(value: string, reason: string) {
  if (!isIsoDate(value)) throw new BookingUrlValidationError(reason);
  return value;
}

function isIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function positiveInt(value: number | undefined, fallback: number) {
  return Number.isInteger(value) && value! >= 1 ? value! : fallback;
}

function nonNegativeInt(value: number | undefined, fallback: number) {
  return Number.isInteger(value) && value! >= 0 ? value! : fallback;
}

function isBudget(value: unknown): value is BookingBudget {
  return value === "budget" || value === "standard" || value === "premium";
}

function sanitizeLabelPart(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

function toIsoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}
