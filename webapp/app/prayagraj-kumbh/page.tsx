import type { Metadata } from "next";
import { KumbhGuidePage } from "@/components/kumbh-portal";
export const metadata: Metadata = { title: "Prayagraj Kumbh Travel Guide", description: "An evergreen planning foundation for future Prayagraj Kumbh and Ardh Kumbh journeys.", alternates: { canonical: "/prayagraj-kumbh" } };
export default function Page() { return <KumbhGuidePage slug="prayagraj-kumbh" />; }
