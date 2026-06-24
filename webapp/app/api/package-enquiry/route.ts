import { NextRequest, NextResponse } from "next/server";
import { createPackageEnquiry, validatePackageEnquiry } from "@/lib/package-enquiries";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null);
    const validation = validatePackageEnquiry(body);
    if (!validation.success) return NextResponse.json({ success: false, error: validation.error }, { status: 400 });

    const referrer = parseReferrer(request.headers.get("referer"), request.url);
    const input = {
      ...validation.data,
      sourcePage: referrer?.pathname || validation.data.sourcePage,
      utmSource: referrer?.searchParams.get("utm_source") || validation.data.utmSource,
      utmMedium: referrer?.searchParams.get("utm_medium") || validation.data.utmMedium,
      utmCampaign: referrer?.searchParams.get("utm_campaign") || validation.data.utmCampaign,
    };
    const result = await createPackageEnquiry(input, request.headers.get("user-agent") || "");
    if (result.duplicate) {
      return NextResponse.json(
        { success: false, error: "We already received this package request recently. Please wait a few minutes or contact support@indiankumbh.com." },
        { status: 409 },
      );
    }

    // TODO: Send an email notification to the IndianKumbh support team.
    // TODO: Append the lead to a Google Sheet for operations.
    // TODO: Sync the enquiry to a CRM.
    // TODO: Trigger an opt-in WhatsApp notification.
    // TODO: Send the lead to an assigned partner webhook after partner-routing rules are approved.

    return NextResponse.json({ success: true, enquiryId: result.enquiry.id });
  } catch {
    return NextResponse.json(
      { success: false, error: "We could not save your enquiry right now. Please try again or email support@indiankumbh.com." },
      { status: 500 },
    );
  }
}

function parseReferrer(value: string | null, base: string) {
  if (!value) return null;
  try {
    return new URL(value, base);
  } catch {
    return null;
  }
}
