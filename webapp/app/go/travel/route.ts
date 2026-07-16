import { NextRequest, NextResponse } from "next/server";
import type { TravelMode } from "@/src/data/travelProviders";
import { buildTravelUrl } from "@/src/lib/travel/buildTravelUrl";
import { logTravelOutboundClick } from "@/src/lib/travel/outbound-clicks";
import { TravelValidationError } from "@/src/lib/travel/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const modes = ["bus", "hotel", "flight", "train"] as const;

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const mode = safe(sp.get("mode")) as TravelMode;
  if (!modes.includes(mode as (typeof modes)[number])) {
    return redirectError(request, mode || "travel", "invalid-mode");
  }

  try {
    const built = buildTravelUrl({
      mode: mode as Exclude<TravelMode, "package">,
      providerId: safe(sp.get("provider")) || undefined,
      fromCitySlug: safe(sp.get("from")) || undefined,
      toCitySlug: safe(sp.get("to")) || undefined,
      citySlug: safe(sp.get("city")) || undefined,
      date: safe(sp.get("date")) || undefined,
      checkin: safe(sp.get("checkin")) || undefined,
      checkout: safe(sp.get("checkout")) || undefined,
      departureDate: safe(sp.get("departureDate")) || undefined,
      returnDate: safe(sp.get("returnDate")) || undefined,
      adults: toInt(sp.get("adults")),
      children: toInt(sp.get("children")),
      rooms: toInt(sp.get("rooms")),
      tripType: sp.get("tripType") === "roundtrip" ? "roundtrip" : "oneway",
      campaign: safe(sp.get("campaign")) || undefined,
      sourcePage: safe(sp.get("sourcePage")) || undefined,
    });

    await logTravelOutboundClick({
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      mode,
      providerId: built.providerId,
      fromCitySlug: safe(sp.get("from")) || undefined,
      toCitySlug: safe(sp.get("to")) || undefined,
      citySlug: safe(sp.get("city")) || undefined,
      date: safe(sp.get("date")) || undefined,
      checkin: safe(sp.get("checkin")) || undefined,
      checkout: safe(sp.get("checkout")) || undefined,
      departureDate: safe(sp.get("departureDate")) || undefined,
      campaign: safe(sp.get("campaign")) || undefined,
      sourcePage: safe(sp.get("sourcePage")) || undefined,
      userAgent: request.headers.get("user-agent") || "",
      referrer: request.headers.get("referer") || "",
      targetHost: new URL(built.url).hostname,
    });

    return NextResponse.redirect(built.url, 307);
  } catch (error) {
    const reason = error instanceof TravelValidationError ? error.safeReason : "invalid-request";
    return redirectError(request, mode, reason);
  }
}

function redirectError(request: NextRequest, mode: string, reason: string) {
  const url = new URL("/travel-search-error", request.url);
  url.searchParams.set("mode", safe(mode) || "travel");
  url.searchParams.set("reason", safe(reason) || "invalid-request");
  return NextResponse.redirect(url, 307);
}

function safe(value: string | null | undefined) {
  return (value || "").replace(/[^\w\s.,/-]/g, "").trim().slice(0, 100);
}

function toInt(value: string | null) {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : undefined;
}
