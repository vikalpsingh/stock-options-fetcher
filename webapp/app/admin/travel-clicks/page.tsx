import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AdminLogin } from "@/components/admin/package-enquiries-admin";
import { TravelClicksAdmin } from "@/components/admin/travel-clicks-admin";
import { adminCookieName, isAdminConfigured, isValidAdminSession } from "@/lib/admin-auth";
import { getTravelOutboundClicks } from "@/src/lib/travel/outbound-clicks";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Travel Clicks Admin", robots: { index: false, follow: false } };

export default async function TravelClicksAdminPage() {
  const cookieStore = await cookies();
  const authenticated = isValidAdminSession(cookieStore.get(adminCookieName)?.value);
  if (!authenticated) return <AdminLogin configured={isAdminConfigured()} />;
  const clicks = (await getTravelOutboundClicks()).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return <TravelClicksAdmin initialClicks={clicks} />;
}
