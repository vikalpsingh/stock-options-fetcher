import { promises as fs } from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { BookingUrlValidationError, buildBookingSearchUrl, getDefaultHotelDates, type BookingBudget } from "@/src/lib/buildBookingUrl";

export const dynamic = "force-dynamic";

const dataDirectory = path.join(process.cwd(), "data");
const outboundClicksFile = path.join(dataDirectory, "outbound-clicks.json");
const budgets = ["budget", "standard", "premium"] as const;

type OutboundClick = {
  id: string;
  provider: "booking";
  city: string;
  checkin: string;
  checkout: string;
  adults: number;
  rooms: number;
  children: number;
  budget?: BookingBudget;
  campaign?: string;
  sourcePage?: string;
  createdAt: string;
  userAgent: string;
  referrer: string;
  targetHost: "booking.com";
};

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const city = safeText(params.get("city") || "ujjain");
  const defaultDates = getDefaultHotelDates(city);
  const checkin = safeText(params.get("checkin") || defaultDates.checkin);
  const checkout = safeText(params.get("checkout") || defaultDates.checkout);
  const adults = toInt(params.get("adults"), 2);
  const rooms = toInt(params.get("rooms"), 1);
  const children = toInt(params.get("children"), 0);
  const budget = normalizeBudget(params.get("budget"));
  const campaign = safeText(params.get("campaign") || "hotel-search");
  const sourcePage = safeText(params.get("sourcePage") || "unknown");

  try {
    const targetUrl = buildBookingSearchUrl({
      citySlug: city,
      checkin,
      checkout,
      adults,
      rooms,
      children,
      budget,
      campaign,
      sourcePage,
    });

    await logOutboundClick({
      id: crypto.randomUUID(),
      provider: "booking",
      city,
      checkin,
      checkout,
      adults,
      rooms,
      children,
      budget,
      campaign,
      sourcePage,
      createdAt: new Date().toISOString(),
      userAgent: request.headers.get("user-agent") || "",
      referrer: request.headers.get("referer") || "",
      targetHost: "booking.com",
    });

    return NextResponse.redirect(targetUrl, 307);
  } catch (error) {
    const reason = error instanceof BookingUrlValidationError ? error.safeReason : "invalid-request";
    const fallback = new URL("/travel-search-error", request.url);
    fallback.searchParams.set("provider", "booking");
    fallback.searchParams.set("reason", reason);
    return NextResponse.redirect(fallback, 307);
  }
}

async function logOutboundClick(click: OutboundClick) {
  await fs.mkdir(dataDirectory, { recursive: true });
  let clicks: OutboundClick[] = [];
  try {
    clicks = JSON.parse(await fs.readFile(outboundClicksFile, "utf8")) as OutboundClick[];
    if (!Array.isArray(clicks)) clicks = [];
  } catch {
    clicks = [];
  }
  clicks.push(click);
  await fs.writeFile(outboundClicksFile, `${JSON.stringify(clicks, null, 2)}\n`, "utf8");
}

function toInt(value: string | null, fallback: number) {
  if (!value) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : fallback;
}

function normalizeBudget(value: string | null): BookingBudget | undefined {
  return budgets.includes(value as BookingBudget) ? value as BookingBudget : undefined;
}

function safeText(value: string) {
  return value.replace(/[^\w\s.,/-]/g, "").trim().slice(0, 80);
}
