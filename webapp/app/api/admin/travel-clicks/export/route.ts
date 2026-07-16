import { NextRequest, NextResponse } from "next/server";
import { requestHasAdminSession } from "@/lib/admin-auth";
import { getTravelOutboundClicks, toTravelClicksCsv } from "@/src/lib/travel/outbound-clicks";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  if (!requestHasAdminSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const csv = toTravelClicksCsv(await getTravelOutboundClicks());
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="travel-clicks-${new Date().toISOString().slice(0, 10)}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
