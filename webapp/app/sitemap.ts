import type { MetadataRoute } from "next";
import { localeCodes } from "@/lib/locale";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = ["", "/plan-my-trip", "/mahakal-temple-guide", "/stay-guide", "/nearby-places", "/food-guide", "/itineraries", "/contact"];
  const englishOnlyRoutes = [
    "/kumbh-mela", "/kumbh-mela/nashik-kumbh-2027", "/kumbh-mela/ujjain-kumbh-2028", "/kumbh-mela/prayagraj-kumbh", "/kumbh-mela/haridwar-kumbh", "/kumbh-mela/kumbh-calendar",
    "/char-dham-yatra", "/char-dham-yatra/registration", "/char-dham-yatra/route-map", "/char-dham-yatra/senior-citizen-guide", "/char-dham-yatra/packages",
    "/12-jyotirlinga", "/12-jyotirlinga/mahakaleshwar-ujjain", "/12-jyotirlinga/omkareshwar", "/12-jyotirlinga/trimbakeshwar", "/12-jyotirlinga/complete-itinerary", "/12-jyotirlinga/senior-citizen-plan",
    "/temple-circuits", "/temple-circuits/ujjain-omkareshwar-maheshwar", "/temple-circuits/nashik-trimbakeshwar-shirdi", "/temple-circuits/varanasi-prayagraj-ayodhya", "/temple-circuits/somnath-dwarka-nageshwar",
    "/sacred-cities", "/sacred-cities/ujjain", "/sacred-cities/nashik", "/sacred-cities/varanasi", "/sacred-cities/ayodhya", "/sacred-cities/haridwar", "/sacred-cities/prayagraj", "/sacred-cities/shirdi",
    "/senior-citizen-yatra", "/packages", "/travel-tools", "/plan-and-book", "/ujjain-kumbh-2028/stay", "/ujjain-kumbh-2028/plan-my-trip", "/ujjain-kumbh-2028/packages", "/privacy", "/disclaimer", "/affiliate-disclosure", "/travel-partner-disclaimer", "/terms",
  ];
  const languages = (route: string) => Object.fromEntries([["en", `https://indiankumbh.com${route}`], ...localeCodes.map((locale) => [locale, `https://indiankumbh.com/${locale}${route}`])]);
  return [...routes.flatMap((route) => [
    { url: `https://indiankumbh.com${route}`, lastModified: new Date(), changeFrequency: route === "" ? "weekly" as const : "monthly" as const, priority: route === "" ? 1 : 0.8, alternates: { languages: languages(route) } },
    ...localeCodes.map((locale) => ({ url: `https://indiankumbh.com/${locale}${route}`, lastModified: new Date(), changeFrequency: route === "" ? "weekly" as const : "monthly" as const, priority: route === "" ? 0.95 : 0.75, alternates: { languages: languages(route) } })),
  ]), ...englishOnlyRoutes.map((route) => ({ url: `https://indiankumbh.com${route}`, lastModified: new Date(), changeFrequency: "monthly" as const, priority: 0.9 }))];
}
