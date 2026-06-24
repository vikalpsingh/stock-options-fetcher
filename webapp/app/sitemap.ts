import type { MetadataRoute } from "next";
import { localeCodes } from "@/lib/locale";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = ["", "/ujjain-kumbh-2028", "/nashik-kumbh-2027", "/prayagraj-kumbh", "/haridwar-kumbh", "/kumbh-calendar", "/plan-my-trip", "/mahakal-temple-guide", "/stay-guide", "/nearby-places", "/food-guide", "/itineraries", "/contact"];
  const englishOnlyRoutes = ["/plan-and-book", "/ujjain-kumbh-2028/packages", "/privacy", "/disclaimer"];
  const languages = (route: string) => Object.fromEntries([["en", `https://indiankumbh.com${route}`], ...localeCodes.map((locale) => [locale, `https://indiankumbh.com/${locale}${route}`])]);
  return [...routes.flatMap((route) => [
    { url: `https://indiankumbh.com${route}`, lastModified: new Date(), changeFrequency: route === "" ? "weekly" as const : "monthly" as const, priority: route === "" ? 1 : 0.8, alternates: { languages: languages(route) } },
    ...localeCodes.map((locale) => ({ url: `https://indiankumbh.com/${locale}${route}`, lastModified: new Date(), changeFrequency: route === "" ? "weekly" as const : "monthly" as const, priority: route === "" ? 0.95 : 0.75, alternates: { languages: languages(route) } })),
  ]), ...englishOnlyRoutes.map((route) => ({ url: `https://indiankumbh.com${route}`, lastModified: new Date(), changeFrequency: "monthly" as const, priority: 0.9 }))];
}
