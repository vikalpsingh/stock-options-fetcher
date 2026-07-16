import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, PackageCheck } from "lucide-react";
import { PilgrimageHero, OfficialDisclaimer, SacredImportanceSection } from "@/src/components/pilgrimage/PilgrimageTemplates";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Pilgrimage Packages and Yatra Quotes", description: "Request package support for Kumbh, Char Dham, Jyotirlinga, senior citizen and temple circuit travel.", alternates: { canonical: "/packages" } };

export default function PackagesPage() {
  return <main><PilgrimageHero eyebrow="Package discovery" title="Pilgrimage Packages" subtitle="Request help for family, senior citizen, group and temple circuit yatras. IndianKumbh.com does not operate tours directly." primaryLabel="Ujjain package quote" primaryHref="/ujjain-kumbh-2028/packages" secondaryLabel="Travel tools" secondaryHref="/travel-tools" /><OfficialDisclaimer /><SacredImportanceSection text="Packages are fulfilled by independent travel partners. Final booking, price, inclusions, cancellation and service terms are confirmed by the partner." points={["Kumbh packages", "Char Dham support", "Senior citizen assisted yatra", "Group/Society trips"]} /><section className="bg-white px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-5xl rounded-[2rem] bg-maroon p-8 text-white sm:p-10"><PackageCheck className="h-10 w-10 text-gold" /><h2 className="mt-5 font-serif text-3xl text-white">Start with Ujjain Kumbh package enquiry</h2><p className="mt-3 text-sm leading-7 text-orange-50/85">The current lead form is ready for Ujjain Kumbh 2028. Broader package categories can reuse this flow as partners are verified.</p><Button asChild className="mt-6"><Link href="/ujjain-kumbh-2028/packages">Open package form<ArrowRight className="h-4 w-4" /></Link></Button></div></section></main>;
}
