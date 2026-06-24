import { NextRequest, NextResponse } from "next/server";
import { requestHasAdminSession } from "@/lib/admin-auth";
import { getPackageEnquiries } from "@/lib/package-enquiries";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  if (!requestHasAdminSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const enquiries = await getPackageEnquiries();
  const headers = ["createdAt", "fullName", "mobile", "whatsappNumber", "email", "sourceCity", "travelMonth", "numberOfAdults", "numberOfChildren", "packageType", "budgetPerPerson", "stayPreference", "hasSeniorCitizens", "needMahakalDarshanSupport", "needTransport", "status", "assignedPartnerId", "sourcePage", "utmSource", "utmMedium", "utmCampaign"];
  const csv = [headers.join(","), ...enquiries.map((item) => headers.map((header) => csvCell(item[header as keyof typeof item])).join(","))].join("\r\n");
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="package-enquiries-${new Date().toISOString().slice(0, 10)}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}

function csvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

