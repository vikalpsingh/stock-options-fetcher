import "server-only";

export type TravelPartnerType =
  | "package_provider"
  | "hotel_affiliate"
  | "ota_affiliate"
  | "official_reference"
  | "local_operator"
  | "api_partner";

export type PartnerIntegrationType = "lead_form" | "affiliate_link" | "manual" | "api_future";
export type TravelPartnerStatus = "prospect" | "active" | "paused";

export type TravelPartner = {
  id: string;
  name: string;
  type: TravelPartnerType;
  integrationType: PartnerIntegrationType;
  supportedDestinations: string[];
  supportedPackageTypes: string[];
  publicDisplayName: string;
  publicDescription: string;
  status: TravelPartnerStatus;
  priority: number;
  internalNotes: string;
};

export type PublicTravelPartner = Omit<TravelPartner, "internalNotes">;

export const travelPartners = ([
  {
    id: "thrillophilia",
    name: "Thrillophilia",
    type: "package_provider",
    integrationType: "lead_form",
    supportedDestinations: ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh"],
    supportedPackageTypes: ["ujjain-family-2n-3d", "ujjain-omkareshwar-maheshwar", "nri-international-visitor"],
    publicDisplayName: "Thrillophilia",
    publicDescription: "Potential provider for curated multi-day packages, stays and local experiences.",
    status: "prospect",
    priority: 1,
    internalNotes: "Confirm pilgrimage inventory, lead terms, brand usage permission, support ownership and cancellation disclosures before activation.",
  },
  {
    id: "booking-com-affiliate",
    name: "Booking.com Affiliate",
    type: "hotel_affiliate",
    integrationType: "affiliate_link",
    supportedDestinations: ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh"],
    supportedPackageTypes: ["ujjain-family-2n-3d", "indore-stay-ujjain-day-trip", "premium-hotel-tent", "nri-international-visitor"],
    publicDisplayName: "Booking.com",
    publicDescription: "Hotel search partner option for comparing available stays on an external booking website.",
    status: "prospect",
    priority: 2,
    internalNotes: "Activate only after affiliate approval and tracking-ID validation. Never imply IndianKumbh controls hotel inventory, payment or refunds.",
  },
  {
    id: "yatra-affiliate",
    name: "Yatra Affiliate",
    type: "ota_affiliate",
    integrationType: "affiliate_link",
    supportedDestinations: ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh"],
    supportedPackageTypes: ["indore-stay-ujjain-day-trip", "premium-hotel-tent", "nri-international-visitor"],
    publicDisplayName: "Yatra",
    publicDescription: "Potential external partner for comparing flights, hotels and other travel options.",
    status: "prospect",
    priority: 3,
    internalNotes: "Confirm current affiliate programme acceptance, permitted deep-link format, attribution window and disclosure requirements.",
  },
  {
    id: "irctc-tourism",
    name: "IRCTC Tourism",
    type: "official_reference",
    integrationType: "manual",
    supportedDestinations: ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh"],
    supportedPackageTypes: ["budget-group-yatra", "senior-citizen-assisted-yatra", "corporate-society-group"],
    publicDisplayName: "IRCTC Tourism",
    publicDescription: "Official reference for available rail-tourism and pilgrimage package information.",
    status: "active",
    priority: 4,
    internalNotes: "Treat as an external official reference, not an endorsed commercial partnership, unless a written agreement is signed.",
  },
  {
    id: "easemytrip-b2b-api",
    name: "EaseMyTrip B2B/API",
    type: "api_partner",
    integrationType: "api_future",
    supportedDestinations: ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh"],
    supportedPackageTypes: ["indore-stay-ujjain-day-trip", "premium-hotel-tent", "nri-international-visitor"],
    publicDisplayName: "EaseMyTrip",
    publicDescription: "Potential future technology partner for travel inventory and booking integrations.",
    status: "prospect",
    priority: 5,
    internalNotes: "Phase 3/4 prospect. Evaluate B2B terms, API cost, support, reconciliation, refunds and Lightsail operational impact before integration.",
  },
  {
    id: "local-ujjain-operator-placeholder",
    name: "Local Ujjain Operator Placeholder",
    type: "local_operator",
    integrationType: "lead_form",
    supportedDestinations: ["ujjain-kumbh-2028"],
    supportedPackageTypes: ["mahakal-darshan-kumbh-snan", "ujjain-family-2n-3d", "senior-citizen-assisted-yatra", "budget-group-yatra", "women-family-safe-travel"],
    publicDisplayName: "Verified Ujjain Travel Partner",
    publicDescription: "Local package and ground-support provider. Identity will be shown only after verification and onboarding.",
    status: "paused",
    priority: 6,
    internalNotes: "Placeholder only. Verify registration, office address, insurance, vehicles, guides, complaint history, pricing, cancellations and emergency escalation before activating.",
  },
  {
    id: "local-indore-hotel-taxi-placeholder",
    name: "Local Indore Hotel + Taxi Operator Placeholder",
    type: "local_operator",
    integrationType: "lead_form",
    supportedDestinations: ["ujjain-kumbh-2028"],
    supportedPackageTypes: ["indore-stay-ujjain-day-trip", "premium-hotel-tent", "senior-citizen-assisted-yatra", "women-family-safe-travel"],
    publicDisplayName: "Verified Indore Stay & Transfer Partner",
    publicDescription: "Indore hotel and Ujjain transfer provider. Identity will be shown only after verification and onboarding.",
    status: "paused",
    priority: 7,
    internalNotes: "Placeholder only. Validate hotel contracts, taxi permits, airport pickup process, driver checks, night support and refund responsibility.",
  },
] satisfies TravelPartner[]).sort((a, b) => a.priority - b.priority);

export function getTravelPartner(id: string) {
  return travelPartners.find((partner) => partner.id === id);
}

export function getPublicActiveTravelPartners(): PublicTravelPartner[] {
  return travelPartners
    .filter((partner) => partner.status === "active")
    .map(({ internalNotes: _internalNotes, ...publicPartner }) => publicPartner);
}

export function getPublicTravelPartner(id: string): PublicTravelPartner | undefined {
  const partner = travelPartners.find((item) => item.id === id && item.status === "active");
  if (!partner) return undefined;
  const { internalNotes: _internalNotes, ...publicPartner } = partner;
  return publicPartner;
}

