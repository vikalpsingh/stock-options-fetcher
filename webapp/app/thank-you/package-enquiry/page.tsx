import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Mail, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Package Enquiry Received",
  description: "Your Ujjain Kumbh package enquiry has been received.",
  robots: { index: false, follow: false },
};

export default function PackageEnquiryThankYou() {
  return (
    <main className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-3xl rounded-[2rem] border border-gold/35 bg-white p-7 text-center shadow-soft sm:p-12">
        <CheckCircle2 className="mx-auto h-16 w-16 text-[#168f4d]" />
        <p className="mt-6 text-xs font-black uppercase tracking-[.2em] text-saffron">Request received</p>
        <h1 className="mt-3 font-serif text-4xl sm:text-5xl">Your package enquiry is with us.</h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-stone-600">Your request has been received. A verified travel partner may contact you after the requirement is reviewed.</p>
        <div className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-left text-sm leading-6 text-amber-950"><ShieldCheck className="mb-2 h-5 w-5 text-amber-700" />IndianKumbh.com does not collect package payments. Confirm the provider identity, final price, inclusions, cancellation and refund terms before booking.</div>
        <p className="mt-6 flex items-center justify-center gap-2 text-sm font-semibold text-stone-700"><Mail className="h-4 w-4 text-saffron" />Questions? support@indiankumbh.com</p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Button asChild><Link href="/plan-and-book">Plan Travel & Stay</Link></Button><Button asChild variant="outline"><Link href="/ujjain-kumbh-2028">Return to Ujjain Guide</Link></Button></div>
      </div>
    </main>
  );
}
