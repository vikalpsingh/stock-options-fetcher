export type TravelMode = "bus" | "hotel" | "flight" | "train" | "package";
export type TravelProviderType = "affiliate_redirect" | "official_reference" | "lead_form" | "api_future";

export type TravelProvider = {
  id: string;
  name: string;
  mode: TravelMode;
  providerType: TravelProviderType;
  baseUrl: string;
  affiliateIdEnvKey?: string;
  campaignPrefixEnvKey?: string;
  defaultCampaignPrefix: string;
  isActive: boolean;
  priority: number;
  supportedCities: string[];
  publicDisclosure: string;
  internalNotes: string;
};

const all = ["ujjain", "indore", "bhopal", "nashik", "prayagraj", "haridwar", "varanasi", "delhi", "mumbai", "pune", "bengaluru", "hyderabad", "ahmedabad", "jaipur", "surat", "nagpur"];

export const travelProviders: TravelProvider[] = [
  { id: "redbus", name: "RedBus", mode: "bus", providerType: "affiliate_redirect", baseUrl: "https://www.redbus.in/search", affiliateIdEnvKey: "REDBUS_AFFILIATE_ID", campaignPrefixEnvKey: "REDBUS_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 1, supportedCities: all, publicDisclosure: "Bus booking is completed on RedBus. IndianKumbh.com may earn a referral commission.", internalNotes: "Verify RedBus city IDs before activating city-pair redirects." },
  { id: "booking", name: "Booking.com", mode: "hotel", providerType: "affiliate_redirect", baseUrl: "https://www.booking.com/searchresults.html", affiliateIdEnvKey: "BOOKING_AFFILIATE_ID", campaignPrefixEnvKey: "BOOKING_LABEL_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 1, supportedCities: all, publicDisclosure: "Hotel booking is completed on Booking.com. IndianKumbh.com may earn a referral commission.", internalNotes: "Use server-side redirect; never include chal_t or force_referer." },
  { id: "easemytrip_flights", name: "EaseMyTrip Flights", mode: "flight", providerType: "affiliate_redirect", baseUrl: "https://www.easemytrip.com/flights.html", affiliateIdEnvKey: "EASEMYTRIP_AFFILIATE_ID", campaignPrefixEnvKey: "EASEMYTRIP_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 1, supportedCities: all, publicDisclosure: "Flight booking is completed on the airline or aggregator website.", internalNotes: "TODO: Verify final deep-link format after affiliate approval." },
  { id: "yatra_flights", name: "Yatra Flights", mode: "flight", providerType: "affiliate_redirect", baseUrl: "https://www.yatra.com/flights", affiliateIdEnvKey: "YATRA_AFFILIATE_ID", campaignPrefixEnvKey: "YATRA_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 2, supportedCities: all, publicDisclosure: "Flight booking is completed on Yatra.", internalNotes: "Fallback flight redirect until primary partner deep links are verified." },
  { id: "yatra_hotels", name: "Yatra Hotels", mode: "hotel", providerType: "affiliate_redirect", baseUrl: "https://www.yatra.com/hotels", affiliateIdEnvKey: "YATRA_AFFILIATE_ID", campaignPrefixEnvKey: "YATRA_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 2, supportedCities: all, publicDisclosure: "Hotel booking is completed on Yatra.", internalNotes: "Fallback hotel redirect." },
  { id: "irctc_tourism", name: "IRCTC Tourism", mode: "train", providerType: "official_reference", baseUrl: "https://www.irctctourism.com/", affiliateIdEnvKey: "IRCTC_AFFILIATE_ID", campaignPrefixEnvKey: "IRCTC_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 1, supportedCities: all, publicDisclosure: "Train booking or package enquiry is completed on official IRCTC/partner websites.", internalNotes: "Do not collect passenger identity or train payment details." },
  { id: "irctc_official_reference", name: "IRCTC Official", mode: "train", providerType: "official_reference", baseUrl: "https://www.irctc.co.in/nget/train-search", campaignPrefixEnvKey: "IRCTC_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 2, supportedCities: all, publicDisclosure: "Train booking is completed on the official IRCTC website.", internalNotes: "Reference link only." },
  { id: "redbus_train", name: "RedBus Train Reference", mode: "train", providerType: "affiliate_redirect", baseUrl: "https://www.redbus.in/railways", affiliateIdEnvKey: "REDBUS_AFFILIATE_ID", campaignPrefixEnvKey: "REDBUS_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 3, supportedCities: all, publicDisclosure: "Train search is completed on partner website.", internalNotes: "Fallback redirect only." },
  { id: "easemytrip_train", name: "EaseMyTrip Train Reference", mode: "train", providerType: "affiliate_redirect", baseUrl: "https://www.easemytrip.com/railways/", affiliateIdEnvKey: "EASEMYTRIP_AFFILIATE_ID", campaignPrefixEnvKey: "EASEMYTRIP_CAMPAIGN_PREFIX", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 4, supportedCities: all, publicDisclosure: "Train search is completed on partner website.", internalNotes: "Fallback redirect only." },
  { id: "package_lead_form", name: "Package enquiry form", mode: "package", providerType: "lead_form", baseUrl: "/ujjain-kumbh-2028/packages", defaultCampaignPrefix: "indiankumbh", isActive: true, priority: 1, supportedCities: ["ujjain", "nashik", "prayagraj", "haridwar"], publicDisclosure: "Packages are fulfilled by independent travel partners.", internalNotes: "Route leads to package enquiry form; Thrillophilia/local operators are handled after qualification." },
];

export function getTravelProvider(id: string) {
  return travelProviders.find((provider) => provider.id === id);
}
