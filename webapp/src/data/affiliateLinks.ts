export type AffiliatePagePlacement =
  | "plan_and_book_travel"
  | "plan_and_book_hotel"
  | "stay_guide"
  | "package_card"
  | "package_results"
  | "footer_reference";

export type AffiliateLink = {
  id: string;
  label: string;
  providerId: string;
  destination: string;
  url: string;
  fallbackUrl: string;
  campaign: string;
  pagePlacement: AffiliatePagePlacement;
  isActive: boolean;
};

const bookingAffiliateId = process.env.NEXT_PUBLIC_BOOKING_AFFILIATE_ID?.trim() || "";
const yatraAffiliateId = process.env.NEXT_PUBLIC_YATRA_AFFILIATE_ID?.trim() || "";

const bookingFallback = "https://www.booking.com/searchresults.html?ss=Ujjain%2C+Madhya+Pradesh%2C+India";
const yatraFallback = "https://www.yatra.com/";

export const affiliateLinks: AffiliateLink[] = [
  {
    id: "booking-ujjain-hotels",
    label: "Compare Ujjain Hotels",
    providerId: "booking-com-affiliate",
    destination: "ujjain-kumbh-2028",
    url: bookingAffiliateId
      ? `${bookingFallback}&aid=${encodeURIComponent(bookingAffiliateId)}&label=indiankumbh-ujjain-2028`
      : bookingFallback,
    fallbackUrl: bookingFallback,
    campaign: "ujjain-kumbh-2028-hotels",
    pagePlacement: "plan_and_book_hotel",
    isActive: Boolean(bookingAffiliateId),
  },
  {
    id: "booking-indore-hotels",
    label: "Compare Indore Hotels",
    providerId: "booking-com-affiliate",
    destination: "ujjain-kumbh-2028",
    url: bookingAffiliateId
      ? `https://www.booking.com/searchresults.html?ss=Indore%2C+Madhya+Pradesh%2C+India&aid=${encodeURIComponent(bookingAffiliateId)}&label=indiankumbh-indore-base`
      : "https://www.booking.com/searchresults.html?ss=Indore%2C+Madhya+Pradesh%2C+India",
    fallbackUrl: "https://www.booking.com/searchresults.html?ss=Indore%2C+Madhya+Pradesh%2C+India",
    campaign: "ujjain-kumbh-2028-indore-stays",
    pagePlacement: "stay_guide",
    isActive: Boolean(bookingAffiliateId),
  },
  {
    id: "booking-bhopal-hotels",
    label: "Compare Bhopal Hotels",
    providerId: "booking-com-affiliate",
    destination: "ujjain-kumbh-2028",
    url: bookingAffiliateId
      ? `https://www.booking.com/searchresults.html?ss=Bhopal%2C+Madhya+Pradesh%2C+India&aid=${encodeURIComponent(bookingAffiliateId)}&label=indiankumbh-bhopal-base`
      : "https://www.booking.com/searchresults.html?ss=Bhopal%2C+Madhya+Pradesh%2C+India",
    fallbackUrl: "https://www.booking.com/searchresults.html?ss=Bhopal%2C+Madhya+Pradesh%2C+India",
    campaign: "ujjain-kumbh-2028-bhopal-stays",
    pagePlacement: "stay_guide",
    isActive: Boolean(bookingAffiliateId),
  },
  {
    id: "yatra-indore-flights",
    label: "Compare Flights to Indore",
    providerId: "yatra-affiliate",
    destination: "ujjain-kumbh-2028",
    url: yatraAffiliateId
      ? `${yatraFallback}?utm_source=indiankumbh&utm_medium=affiliate&utm_campaign=ujjain-kumbh-2028-indore-flights&affiliate_id=${encodeURIComponent(yatraAffiliateId)}`
      : yatraFallback,
    fallbackUrl: yatraFallback,
    campaign: "ujjain-kumbh-2028-indore-flights",
    pagePlacement: "plan_and_book_travel",
    isActive: Boolean(yatraAffiliateId),
  },
  {
    id: "yatra-ujjain-hotels",
    label: "Compare Ujjain Hotels on Yatra",
    providerId: "yatra-affiliate",
    destination: "ujjain-kumbh-2028",
    url: yatraAffiliateId
      ? `${yatraFallback}?utm_source=indiankumbh&utm_medium=affiliate&utm_campaign=ujjain-kumbh-2028-hotels&affiliate_id=${encodeURIComponent(yatraAffiliateId)}`
      : yatraFallback,
    fallbackUrl: yatraFallback,
    campaign: "ujjain-kumbh-2028-yatra-hotels",
    pagePlacement: "plan_and_book_hotel",
    isActive: Boolean(yatraAffiliateId),
  },
  {
    id: "irctc-pilgrimage-packages",
    label: "Check IRCTC Pilgrimage Packages",
    providerId: "irctc-tourism",
    destination: "ujjain-kumbh-2028",
    url: "https://www.irctctourism.com/",
    fallbackUrl: "https://www.irctctourism.com/",
    campaign: "ujjain-kumbh-2028-official-reference",
    pagePlacement: "package_results",
    isActive: true,
  },
];

export function getAffiliateLink(id: string) {
  return affiliateLinks.find((link) => link.id === id);
}

export function getActiveAffiliateLinks(destination: string, pagePlacement?: AffiliatePagePlacement) {
  return affiliateLinks.filter(
    (link) => link.isActive && link.destination === destination && (!pagePlacement || link.pagePlacement === pagePlacement),
  );
}
