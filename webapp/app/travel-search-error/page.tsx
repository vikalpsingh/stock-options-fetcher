import type { Metadata } from "next";
import Link from "next/link";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Travel Search Error",
  description: "A travel partner search link could not be opened safely.",
  robots: { index: false, follow: false },
};

export default async function TravelSearchErrorPage({ searchParams }: { searchParams: Promise<{ provider?: string; reason?: string }> }) {
  const params = await searchParams;
  const provider = params.provider === "booking" ? "Booking.com" : "the travel partner";
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-3xl rounded-[2rem] border border-amber-200 bg-white p-6 text-center shadow-soft sm:p-10">
        <AlertTriangle className="mx-auto h-12 w-12 text-amber-700" />
        <h1 className="mt-5 font-serif text-4xl font-semibold text-ink">We could not open this travel search safely</h1>
        <p className="mt-5 leading-8 text-stone-600">The {provider} link had missing or invalid planning details. Please choose your city, dates and traveller count again.</p>
        <p className="mt-3 text-xs text-stone-400">Reason: {params.reason || "invalid-request"}</p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild><Link href="/plan-and-book">Plan and Book<ArrowRight className="h-4 w-4" /></Link></Button>
          <Button asChild variant="outline"><Link href="/stay-guide">Compare stay cities</Link></Button>
        </div>
      </div>
    </main>
  );
}
