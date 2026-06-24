import type { Metadata } from "next";
import { KumbhGuidePage } from "@/components/kumbh-portal";
export const metadata: Metadata = { title: "Haridwar Kumbh Travel Guide", description: "An evergreen foundation for Haridwar Kumbh planning, Har Ki Pauri and Ganga pilgrimage travel.", alternates: { canonical: "/haridwar-kumbh" } };
export default function Page() { return <KumbhGuidePage slug="haridwar-kumbh" />; }
