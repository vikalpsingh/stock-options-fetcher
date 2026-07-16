"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, Languages, Menu, Search, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getPathLocale, localeCodes, localeNames, localizedHref, switchLocaleHref } from "@/lib/locale";
import { uiCopy } from "@/data/locale-ui";
import { portalCopy } from "@/data/kumbh-portal";
import { SearchDialog } from "./search-dialog";
import { Button } from "./ui/button";

const navigationTerms = {
  en: { allKumbhs: "All Kumbhs", focusGuide: "Focus Guide" },
  hi: { allKumbhs: "सभी कुंभ", focusGuide: "मुख्य गाइड" },
  bn: { allKumbhs: "সব কুম্ভ", focusGuide: "প্রধান গাইড" },
  mr: { allKumbhs: "सर्व कुंभ", focusGuide: "मुख्य मार्गदर्शक" },
  te: { allKumbhs: "అన్ని కుంభాలు", focusGuide: "ప్రధాన గైడ్" },
  ta: { allKumbhs: "அனைத்து கும்பங்கள்", focusGuide: "முதன்மை வழிகாட்டி" },
  kn: { allKumbhs: "ಎಲ್ಲಾ ಕುಂಭಗಳು", focusGuide: "ಮುಖ್ಯ ಮಾರ್ಗದರ್ಶಿ" },
} as const;

export function Header() {
  const pathname = usePathname();
  const locale = getPathLocale(pathname);
  const copy = locale === "en" ? null : uiCopy[locale];
  const portal = portalCopy[locale];
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState(false);
  const [languagesOpen, setLanguagesOpen] = useState(false);
  const [kumbhsOpen, setKumbhsOpen] = useState(false);
  const [mobileKumbhsOpen, setMobileKumbhsOpen] = useState(false);
  const kumbhMenuRef = useRef<HTMLDivElement>(null);
  const labels = portal.nav;
  const terms = navigationTerms[locale];

  const navItems = locale === "en" ? [
    { label: "Kumbh Mela", path: "/kumbh-mela", focus: true },
    { label: "Char Dham", path: "/char-dham-yatra" },
    { label: "Jyotirlinga", path: "/12-jyotirlinga" },
    { label: "Temple Circuits", path: "/temple-circuits" },
    { label: "Sacred Cities", path: "/sacred-cities" },
    { label: "Packages", path: "/packages" },
    { label: "Travel Tools", path: "/travel-tools" },
  ] : [
    { label: labels[1], path: "/ujjain-kumbh-2028", focus: true },
    { label: labels[5], path: "/plan-my-trip" },
    { label: labels[3], path: "/mahakal-temple-guide" },
    { label: labels[4], path: "/stay-guide" },
  ];
  const kumbhPaths = [
    { path: "/kumbh-mela/nashik-kumbh-2027", label: "Nashik-Trimbakeshwar 2027", focus: true },
    { path: "/kumbh-mela/ujjain-kumbh-2028", label: "Ujjain Simhastha 2028", focus: false },
    { path: "/kumbh-mela/prayagraj-kumbh", label: "Prayagraj Kumbh", focus: false },
    { path: "/kumbh-mela/haridwar-kumbh", label: "Haridwar Kumbh", focus: false },
    { path: "/kumbh-mela/kumbh-calendar", label: "Kumbh Calendar", focus: false },
  ] as const;
  const allKumbhsLabel = locale === "en" ? "Kumbh Mela" : terms.allKumbhs;
  const blogLabel = locale === "en" ? "Blog" : portal.latestTitle;
  const planHref = localizedHref(locale === "en" ? "/plan-and-book" : "/plan-my-trip", locale);

  useEffect(() => {
    function closeDropdown(event: MouseEvent) {
      if (kumbhMenuRef.current && !kumbhMenuRef.current.contains(event.target as Node)) setKumbhsOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setKumbhsOpen(false);
    }
    document.addEventListener("mousedown", closeDropdown);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeDropdown);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  function isActive(path: string) {
    return pathname === localizedHref(path, locale);
  }

  return (
    <>
      <div className="bg-maroon px-4 py-2 text-center text-[11px] font-semibold tracking-wide text-orange-50">
        {copy?.notice || "Independent planning guide · Confirm final 2028 dates and arrangements with official authorities"}
      </div>
      <header className="sticky top-0 z-40 border-b border-stone-200/80 bg-cream/95 backdrop-blur-xl print:hidden">
        <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href={localizedHref("/", locale)} className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-maroon font-serif text-xl text-gold ring-4 ring-orange-100">ॐ</span>
            <span className="min-w-0">
              <span className="block font-serif text-base font-bold leading-none text-ink sm:text-lg">{portal.brand}</span>
              <span className="mt-1 block max-w-44 truncate text-[9px] font-extrabold uppercase tracking-[0.12em] text-saffron">{portal.tagline}</span>
            </span>
          </Link>

          <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary navigation">
            {navItems.map((item) => {
              const href = localizedHref(item.path, locale);
              return (
                <Link
                  key={item.path}
                  href={href}
                  className={`relative rounded-full px-3 py-2 text-[13px] font-semibold transition hover:bg-white hover:text-saffron ${
                    isActive(item.path) ? "text-saffron" : "text-stone-700"
                  } ${item.focus ? "border border-gold/50 bg-amber-50 pr-3" : ""}`}
                >
                  <span className="flex items-center gap-1.5">
                    {item.focus && <Sparkles className="h-3.5 w-3.5 text-gold-dark" />}
                    {item.label}
                  </span>
                  {item.focus && <span className="absolute -top-2 right-2 rounded-full bg-maroon px-1.5 py-0.5 text-[7px] font-black uppercase tracking-wider text-gold">{terms.focusGuide}</span>}
                </Link>
              );
            })}

            <div ref={kumbhMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setKumbhsOpen((value) => !value)}
                aria-expanded={kumbhsOpen}
                aria-haspopup="menu"
                className={`flex items-center gap-1 rounded-full px-3 py-2 text-[13px] font-semibold transition hover:bg-white hover:text-saffron ${
                  kumbhPaths.some((item) => isActive(item.path)) && !isActive("/ujjain-kumbh-2028") ? "text-saffron" : "text-stone-700"
                }`}
              >
                {allKumbhsLabel}
                <ChevronDown className={`h-4 w-4 transition ${kumbhsOpen ? "rotate-180" : ""}`} />
              </button>
              {kumbhsOpen && (
                <div role="menu" className="absolute left-1/2 top-12 w-72 -translate-x-1/2 rounded-2xl border border-gold/30 bg-white p-2 shadow-2xl shadow-maroon/10">
                  {kumbhPaths.map((item) => (
                    <Link
                      role="menuitem"
                      key={item.path}
                      href={localizedHref(item.path, locale)}
                      onClick={() => setKumbhsOpen(false)}
                      className={`flex items-center justify-between rounded-xl px-3 py-3 text-sm font-semibold transition hover:bg-sand ${
                        isActive(item.path) ? "bg-orange-50 text-saffron" : "text-stone-700"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.focus && <span className="rounded-full bg-maroon px-2 py-1 text-[8px] font-black uppercase tracking-wider text-gold">{terms.focusGuide}</span>}
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <Link href={localizedHref("/#latest-guides", locale)} className="rounded-full px-3 py-2 text-[13px] font-semibold text-stone-700 transition hover:bg-white hover:text-saffron">
              {blogLabel}
            </Link>
          </nav>

          <div className="flex items-center gap-1">
            <button onClick={() => setSearch(true)} className="grid h-10 w-10 place-items-center rounded-full hover:bg-white" aria-label={copy?.search || "Search"}>
              <Search className="h-5 w-5" />
            </button>
            <div className="relative hidden sm:block">
              <button onClick={() => setLanguagesOpen((value) => !value)} className="flex h-10 items-center gap-1.5 rounded-full px-3 text-xs font-bold text-stone-600 hover:bg-white">
                <Languages className="h-4 w-4" />
                {localeNames[locale]}
              </button>
              {languagesOpen && (
                <div className="absolute right-0 top-12 w-44 overflow-hidden rounded-2xl border border-stone-200 bg-white p-2 shadow-xl">
                  {(["en", ...localeCodes] as const).map((code) => (
                    <Link
                      key={code}
                      href={switchLocaleHref(pathname, code)}
                      onClick={() => setLanguagesOpen(false)}
                      className={`block rounded-xl px-3 py-2.5 text-sm font-semibold hover:bg-sand ${locale === code ? "bg-orange-50 text-saffron" : ""}`}
                    >
                      {localeNames[code]}
                    </Link>
                  ))}
                </div>
              )}
            </div>
            <button onClick={() => setOpen(!open)} className="grid h-10 w-10 place-items-center rounded-full lg:hidden" aria-expanded={open} aria-label={copy?.menu || "Menu"}>
              {open ? <X /> : <Menu />}
            </button>
          </div>
        </div>

        {open && (
          <nav className="max-h-[calc(100vh-104px)] overflow-y-auto border-t border-stone-200 bg-cream px-4 pb-5 lg:hidden" aria-label="Mobile navigation">
            {navItems.map((item) => (
              <Link
                key={item.path}
                href={localizedHref(item.path, locale)}
                onClick={() => setOpen(false)}
                className={`flex items-center justify-between border-b border-stone-200 py-3.5 text-sm font-semibold ${isActive(item.path) ? "text-saffron" : ""}`}
              >
                <span className="flex items-center gap-2">{item.focus && <Sparkles className="h-4 w-4 text-gold-dark" />}{item.label}</span>
                {item.focus && <span className="rounded-full bg-maroon px-2 py-1 text-[8px] font-black uppercase tracking-wider text-gold">{terms.focusGuide}</span>}
              </Link>
            ))}

            <button
              type="button"
              onClick={() => setMobileKumbhsOpen((value) => !value)}
              aria-expanded={mobileKumbhsOpen}
              className="flex w-full items-center justify-between border-b border-stone-200 py-3.5 text-left text-sm font-semibold"
            >
              {allKumbhsLabel}
              <ChevronDown className={`h-4 w-4 transition ${mobileKumbhsOpen ? "rotate-180" : ""}`} />
            </button>
            {mobileKumbhsOpen && (
              <div className="border-b border-stone-200 bg-white/60 px-2 py-2">
                {kumbhPaths.map((item) => (
                  <Link
                    key={item.path}
                    href={localizedHref(item.path, locale)}
                    onClick={() => setOpen(false)}
                    className={`flex items-center justify-between rounded-xl px-3 py-3 text-sm font-medium hover:bg-white ${isActive(item.path) ? "bg-orange-50 text-saffron" : ""}`}
                  >
                    {item.label}
                    {item.focus && <span className="text-[9px] font-black uppercase tracking-wider text-maroon">{terms.focusGuide}</span>}
                  </Link>
                ))}
              </div>
            )}

            <Link href={localizedHref("/#latest-guides", locale)} onClick={() => setOpen(false)} className="block border-b border-stone-200 py-3.5 text-sm font-semibold">
              {blogLabel}
            </Link>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <select
                value={locale}
                onChange={(event) => {
                  window.location.href = switchLocaleHref(pathname, event.target.value as typeof locale);
                }}
                className="rounded-full border border-stone-300 bg-white px-4 text-sm font-bold"
                aria-label="Select language"
              >
                {(["en", ...localeCodes] as const).map((code) => <option key={code} value={code}>{localeNames[code]}</option>)}
              </select>
              <Button asChild variant="maroon"><Link href={planHref}>{copy?.planTrip || "Plan trip"}</Link></Button>
            </div>
          </nav>
        )}
      </header>
      <SearchDialog open={search} onClose={() => setSearch(false)} locale={locale} />
    </>
  );
}
