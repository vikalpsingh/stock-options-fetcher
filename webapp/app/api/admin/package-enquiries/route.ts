import { NextRequest, NextResponse } from "next/server";
import { requestHasAdminSession } from "@/lib/admin-auth";
import { enquiryStatuses, getPackageEnquiries, updatePackageEnquiry } from "@/lib/package-enquiries";
import { travelPartners } from "@/src/data/travelPartners";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  if (!requestHasAdminSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const enquiries = await getPackageEnquiries();
  return NextResponse.json({ enquiries: enquiries.sort((a, b) => b.createdAt.localeCompare(a.createdAt)) });
}

export async function PATCH(request: NextRequest) {
  if (!requestHasAdminSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const body = await request.json().catch(() => ({})) as { id?: string; status?: string; assignedPartnerId?: string | null };
  if (!body.id) return NextResponse.json({ error: "Enquiry ID is required." }, { status: 400 });
  if (body.status && !enquiryStatuses.includes(body.status as (typeof enquiryStatuses)[number])) return NextResponse.json({ error: "Invalid status." }, { status: 400 });
  if (body.assignedPartnerId && !travelPartners.some((partner) => partner.id === body.assignedPartnerId)) return NextResponse.json({ error: "Invalid partner." }, { status: 400 });

  try {
    const enquiry = await updatePackageEnquiry(body.id, {
      ...(body.status ? { status: body.status as (typeof enquiryStatuses)[number] } : {}),
      ...("assignedPartnerId" in body ? { assignedPartnerId: body.assignedPartnerId || null } : {}),
    });
    return NextResponse.json({ success: true, enquiry });
  } catch {
    return NextResponse.json({ error: "Enquiry not found." }, { status: 404 });
  }
}

