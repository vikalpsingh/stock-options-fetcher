import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AdminLogin, PackageEnquiriesAdmin } from "@/components/admin/package-enquiries-admin";
import { adminCookieName, isAdminConfigured, isValidAdminSession } from "@/lib/admin-auth";
import { getPackageEnquiries } from "@/lib/package-enquiries";
import { travelPartners } from "@/src/data/travelPartners";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Package Enquiries Admin", robots: { index: false, follow: false } };

export default async function PackageEnquiriesAdminPage() {
  const cookieStore = await cookies();
  const authenticated = isValidAdminSession(cookieStore.get(adminCookieName)?.value);
  if (!authenticated) return <AdminLogin configured={isAdminConfigured()} />;
  const enquiries = (await getPackageEnquiries()).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  const partners = travelPartners.map((partner) => ({ id: partner.id, name: partner.name, status: partner.status }));
  return <PackageEnquiriesAdmin initialEnquiries={enquiries} partners={partners} />;
}
