export type HotelAffiliateLink = {
  id: string;
  citySlug: string;
  label: string;
  campaign: string;
  sourcePage: string;
  priority: number;
  isActive: boolean;
};

export const hotelAffiliateLinks: HotelAffiliateLink[] = [
  {
    id: "booking-ujjain-kumbh-hotels",
    citySlug: "ujjain",
    label: "Check Ujjain Hotels",
    campaign: "ujjain-kumbh-2028",
    sourcePage: "hotel-cta",
    priority: 1,
    isActive: true,
  },
  {
    id: "booking-indore-kumbh-hotels",
    citySlug: "indore",
    label: "Check Indore Hotels",
    campaign: "ujjain-kumbh-2028",
    sourcePage: "hotel-cta",
    priority: 2,
    isActive: true,
  },
  {
    id: "booking-bhopal-kumbh-hotels",
    citySlug: "bhopal",
    label: "Check Bhopal Hotels",
    campaign: "ujjain-kumbh-2028",
    sourcePage: "hotel-cta",
    priority: 3,
    isActive: true,
  },
];
