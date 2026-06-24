import type { Metadata } from "next";
import { KumbhGuidePage } from "@/components/kumbh-portal";
export const metadata: Metadata = { title: "Kumbh Mela Calendar and Planning Status", description: "Track planning horizons and official schedule status for Ujjain, Nashik, Prayagraj and Haridwar Kumbh guides.", alternates: { canonical: "/kumbh-calendar" } };
export default function Page() { return <KumbhGuidePage slug="kumbh-calendar" />; }
