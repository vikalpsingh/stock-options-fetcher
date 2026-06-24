export const localeCodes = ["hi", "bn", "mr", "te", "ta", "kn"] as const;
export type LocaleCode = (typeof localeCodes)[number];

export const localeNames: Record<LocaleCode | "en", string> = {
  en: "English",
  hi: "हिन्दी",
  bn: "বাংলা",
  mr: "मराठी",
  te: "తెలుగు",
  ta: "தமிழ்",
  kn: "ಕನ್ನಡ",
};

export function isLocaleCode(value: string): value is LocaleCode {
  return localeCodes.includes(value as LocaleCode);
}

export function getPathLocale(pathname: string): LocaleCode | "en" {
  const segment = pathname.split("/")[1];
  return isLocaleCode(segment) ? segment : "en";
}

export function stripLocale(pathname: string) {
  const locale = getPathLocale(pathname);
  if (locale === "en") return pathname || "/";
  return pathname.replace(new RegExp(`^/${locale}(?=/|$)`), "") || "/";
}

export function localizedHref(href: string, locale: LocaleCode | "en") {
  const clean = stripLocale(href);
  if (locale === "en") return clean;
  return clean === "/" ? `/${locale}` : `/${locale}${clean}`;
}

export function switchLocaleHref(pathname: string, locale: LocaleCode | "en") {
  return localizedHref(stripLocale(pathname), locale);
}
