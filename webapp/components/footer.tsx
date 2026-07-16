"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mail, MapPin, ShieldCheck } from "lucide-react";
import { getPathLocale, localizedHref } from "@/lib/locale";
import { uiCopy } from "@/data/locale-ui";
import { portalCopy } from "@/data/kumbh-portal";

export function Footer() {
  const locale = getPathLocale(usePathname());
  const copy = locale === "en" ? null : uiCopy[locale];
  const portal = portalCopy[locale];
  const href = (path: string) => localizedHref(path, locale);

  return (
    <footer className="pattern-mandala bg-[#211615] pb-20 text-stone-300 md:pb-0 print:hidden">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-2 lg:grid-cols-4 lg:px-8">
        <div>
          <div className="font-serif text-2xl font-bold text-white">{portal.brand}</div>
          <p className="mt-1 text-xs font-bold uppercase tracking-widest text-gold">{portal.tagline}</p>
          <p className="mt-4 max-w-sm text-sm leading-6 text-stone-400">{portal.focusNotice}</p>
        </div>
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-widest text-gold">{copy?.footerPlan || "Plan"}</p>
          <div className="space-y-3 text-sm">
            <Link className="block hover:text-white" href={href(locale === "en" ? "/plan-and-book" : "/plan-my-trip")}>{copy?.planTrip || "Plan my trip"}</Link>
            <Link className="block hover:text-white" href={href("/stay-guide")}>{copy?.compareStays || "Compare stays"}</Link>
            <Link className="block hover:text-white" href={href("/itineraries")}>{copy?.itineraries || "Itineraries"}</Link>
            {locale === "en" && <Link className="block hover:text-white" href="/ujjain-kumbh-2028/packages">Ujjain packages</Link>}
          </div>
        </div>
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-widest text-gold">{copy?.footerDiscover || "Kumbh cities"}</p>
          <div className="space-y-3 text-sm">
            <Link className="block hover:text-white" href={href("/ujjain-kumbh-2028")}>Ujjain 2028</Link>
            <Link className="block hover:text-white" href={href("/nashik-kumbh-2027")}>Nashik 2027</Link>
            <Link className="block hover:text-white" href={href("/kumbh-calendar")}>Kumbh Calendar</Link>
          </div>
        </div>
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-widest text-gold">{copy?.footerTrust || "Trust & support"}</p>
          <p className="flex gap-2 text-sm"><ShieldCheck className="h-4 w-4 text-gold" />{copy?.officialFirst || "Official sources first"}</p>
          <Link href={href("/contact")} className="mt-4 flex gap-2 text-sm hover:text-white"><Mail className="h-4 w-4" />{copy?.enquiry || "Travel enquiry"}</Link>
          <a href="mailto:support@indiankumbh.com" className="mt-4 flex gap-2 text-sm hover:text-white"><Mail className="h-4 w-4" />support@indiankumbh.com</a>
          <p className="mt-4 flex gap-2 text-sm text-stone-400"><MapPin className="h-4 w-4" />{copy?.location || "Ujjain, Madhya Pradesh"}</p>
        </div>
      </div>
      <div className="border-t border-white/10 px-4 py-5 text-center text-xs leading-5 text-stone-500">
        <p>Dates, routes and official arrangements should be verified with government/official sources before travel.</p>
        <p className="mt-2">
          © 2026 IndianKumbh · <Link href="/affiliate-disclosure" className="hover:text-white">Affiliate Disclosure</Link> · <Link href="/travel-partner-disclaimer" className="hover:text-white">Travel Partner Disclaimer</Link> · <Link href="/privacy" className="hover:text-white">Privacy Policy</Link> · <Link href="/terms" className="hover:text-white">Terms</Link>
        </p>
      </div>
    </footer>
  );
}
