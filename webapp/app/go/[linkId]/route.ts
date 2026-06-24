import { NextRequest, NextResponse } from "next/server";
import { getAffiliateLink } from "@/src/data/affiliateLinks";
import { logAffiliateClick } from "@/lib/package-enquiries";

export const runtime = "nodejs";

export async function GET(request: NextRequest, { params }: { params: Promise<{ linkId: string }> }) {
  const { linkId } = await params;
  const link = getAffiliateLink(linkId);
  if (!link) return NextResponse.redirect(new URL("/plan-and-book", request.url), 307);

  await logAffiliateClick({
    linkId: link.id,
    providerId: link.providerId,
    destination: link.destination,
    campaign: link.campaign,
    sourcePage: request.nextUrl.searchParams.get("source")?.slice(0, 300) || "",
    userAgent: (request.headers.get("user-agent") || "").slice(0, 500),
    referrer: (request.headers.get("referer") || "").slice(0, 500),
  }).catch(() => undefined);

  return NextResponse.redirect(link.isActive ? link.url : link.fallbackUrl, 307);
}

