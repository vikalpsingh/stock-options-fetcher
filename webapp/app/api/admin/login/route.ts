import { NextRequest, NextResponse } from "next/server";
import { isAdminConfigured, setAdminSessionCookie, verifyAdminPassword } from "@/lib/admin-auth";

export async function POST(request: NextRequest) {
  if (!isAdminConfigured()) return NextResponse.json({ success: false, error: "ADMIN_PASSWORD is not configured." }, { status: 503 });
  const body = await request.json().catch(() => ({})) as { password?: string };
  if (!verifyAdminPassword(body.password || "")) return NextResponse.json({ success: false, error: "Incorrect password." }, { status: 401 });
  const response = NextResponse.json({ success: true });
  setAdminSessionCookie(response);
  return response;
}

