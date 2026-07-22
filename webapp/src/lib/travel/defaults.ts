export type TravelWidgetDefaults = {
  defaultFromCity: string;
  defaultToCity: string;
  defaultHotelCity: string;
  defaultFlightToCity: string;
  packageHref: string;
};

export function inferTravelDefaults({
  sourcePage,
  campaign,
  title,
}: {
  sourcePage: string;
  campaign: string;
  title: string;
}): TravelWidgetDefaults {
  const context = `${sourcePage} ${campaign} ${title}`.toLowerCase();
  if (context.includes("nashik") || context.includes("trimbakeshwar")) {
    return { defaultFromCity: "pune", defaultToCity: "nashik", defaultHotelCity: "nashik", defaultFlightToCity: "nashik", packageHref: "/kumbh-mela/nashik-kumbh-2027/packages" };
  }
  if (context.includes("prayagraj") || context.includes("sangam")) {
    return { defaultFromCity: "delhi", defaultToCity: "prayagraj", defaultHotelCity: "prayagraj", defaultFlightToCity: "prayagraj", packageHref: "/kumbh-mela/prayagraj-kumbh/packages" };
  }
  if (context.includes("haridwar") || context.includes("rishikesh")) {
    return { defaultFromCity: "delhi", defaultToCity: "haridwar", defaultHotelCity: "haridwar", defaultFlightToCity: "haridwar", packageHref: "/kumbh-mela/haridwar-kumbh/packages" };
  }
  if (context.includes("varanasi") || context.includes("kashi")) {
    return { defaultFromCity: "delhi", defaultToCity: "varanasi", defaultHotelCity: "varanasi", defaultFlightToCity: "varanasi", packageHref: "/packages" };
  }
  if (context.includes("ujjain") || context.includes("mahakal") || context.includes("omkareshwar") || context.includes("maheshwar")) {
    return { defaultFromCity: "bengaluru", defaultToCity: "ujjain", defaultHotelCity: "ujjain", defaultFlightToCity: "ujjain", packageHref: "/kumbh-mela/ujjain-kumbh-2028/packages" };
  }
  return { defaultFromCity: "delhi", defaultToCity: "nashik", defaultHotelCity: "nashik", defaultFlightToCity: "nashik", packageHref: "/packages" };
}
