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
const redbusHostPattern = /(^|\.)redbus\.in$/i;
const bookingHostPattern = /(^|\.)booking\.com$/i;

const redbusCityNames: Record<string, string> = {
  ahmedabad: "Ahmedabad",
  bangalore: "Bangalore",
  bengaluru: "Bangalore",
  bhopal: "Bhopal",
  delhi: "Delhi",
  indore: "Indore",
  mumbai: "Mumbai",
  pune: "Pune",
  ujjain: "Ujjain",
};

export function generateAffiliateLinks(
  input: TripPlannerInput,
  recommendation: TripRecommendation,
  config: AffiliateLinkConfig,
): AffiliateLinks {
  const travelBaseUrl = config.travelBaseUrl || travelFallback;
  const hotelBaseUrl = config.hotelBaseUrl || hotelFallback;
  return {
    travelUrl: buildTravelUrl(travelBaseUrl, input, recommendation),
    hotelUrl: buildHotelUrl(hotelBaseUrl, input, recommendation),
    travelPartnerConfigured: Boolean(config.travelBaseUrl),
    hotelPartnerConfigured: Boolean(config.hotelBaseUrl),
  };
}

function buildTravelUrl(baseUrl: string, input: TripPlannerInput, recommendation: TripRecommendation) {
  if (isRedbusUrl(baseUrl)) {
    return buildRedbusSearchUrl(baseUrl, input, recommendation);
  }

  return withQuery(baseUrl, {
    fromCity: input.fromCity,
    destinationCity: recommendation.destinationCity,
    travelDate: input.travelDate,
    returnDate: input.returnDate,
    travellersCount: String(input.travellersCount),
    travelMode: input.travelMode,
  });
}

function buildHotelUrl(baseUrl: string, input: TripPlannerInput, recommendation: TripRecommendation) {
  if (isBookingUrl(baseUrl)) {
    return buildBookingSearchUrl(baseUrl, input, recommendation);
  }

  return withQuery(baseUrl, {
    destinationCity: recommendation.stayCity,
    checkin: input.travelDate,
    checkout: input.returnDate,
    travellersCount: String(input.travellersCount),
    budget: input.budget,
  });
}

function buildBookingSearchUrl(baseUrl: string, input: TripPlannerInput, recommendation: TripRecommendation) {
  void baseUrl;
  const checkin = input.travelDate;
  const checkout = normalizeHotelCheckout(input.travelDate, input.returnDate);
  return withQuery("/go/booking", {
    city: recommendation.stayCity.toLowerCase(),
    checkin,
    checkout,
    adults: String(Math.max(1, input.travellersCount)),
    rooms: String(Math.max(1, Math.ceil(input.travellersCount / 2))),
    children: "0",
    budget: input.budget,
    campaign: "plan-and-book",
    sourcePage: "plan-and-book",
  });
}

function buildRedbusSearchUrl(baseUrl: string, input: TripPlannerInput, recommendation: TripRecommendation) {
  const fromCityName = normalizeRedbusCityName(input.fromCity);
  const toCityName = normalizeRedbusCityName(recommendation.destinationCity);
  const onward = formatRedbusDate(input.travelDate);

  return withQuery(
    stripUndefinedRedbusCityIds(baseUrl),
    {
      fromCityName,
      toCityName,
      onward,
      doj: onward,
      src: fromCityName,
      dst: toCityName,
      travellersCount: String(input.travellersCount),
    },
    { dropEmptyValues: true },
  );
}

function isBookingUrl(baseUrl: string) {
  try {
    const host = new URL(baseUrl).hostname;
    return bookingHostPattern.test(host);
  } catch {
    return /booking\.com/i.test(baseUrl);
  }
}

function isRedbusUrl(baseUrl: string) {
  try {
    const host = new URL(baseUrl).hostname;
    return redbusHostPattern.test(host);
  } catch {
    return /redbus\.in/i.test(baseUrl);
  }
}

function stripUndefinedRedbusCityIds(baseUrl: string) {
  try {
    const url = new URL(baseUrl);
    ["fromCityId", "toCityId"].forEach((key) => {
      const value = url.searchParams.get(key);
      if (!value || value.toLowerCase() === "undefined" || value.toLowerCase() === "null") {
        url.searchParams.delete(key);
      }
    });
    return url.toString();
  } catch {
    return baseUrl
      .replace(/([?&])(fromCityId|toCityId)=(undefined|null)?(?=&|$)/gi, "$1")
      .replace(/[?&]$/, "");
  }
}

function normalizeHotelCheckout(checkin: string, checkout: string) {
  if (!isIsoDate(checkin) || !isIsoDate(checkout) || checkout > checkin) return checkout;
  return addDays(checkin, 1);
}

function addDays(date: string, days: number) {
  const [year, month, day] = date.split("-").map(Number);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  utcDate.setUTCDate(utcDate.getUTCDate() + days);
  return utcDate.toISOString().slice(0, 10);
}

function isIsoDate(date: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(date);
}

function normalizeRedbusCityName(city: string) {
  const cleaned = city.trim().replace(/\s+/g, " ");
  return redbusCityNames[cleaned.toLowerCase()] || cleaned;
}

function formatRedbusDate(date: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return date;
  const [, year, month, day] = match;
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthIndex = Number(month) - 1;
  if (monthIndex < 0 || monthIndex > 11) return date;
  return `${day}-${monthNames[monthIndex]}-${year}`;
}

function withQuery(baseUrl: string, values: Record<string, string>, options: { dropEmptyValues?: boolean } = {}) {
  try {
    const url = new URL(baseUrl);
    Object.entries(values).forEach(([key, value]) => {
      if (value) {
        url.searchParams.set(key, value);
      } else if (options.dropEmptyValues) {
        url.searchParams.delete(key);
      }
    });
    return url.toString();
  } catch {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value || !options.dropEmptyValues) params.set(key, value);
    });
    const separator = baseUrl.includes("?") ? "&" : "?";
    return `${baseUrl}${separator}${params.toString()}`;
  }
}
