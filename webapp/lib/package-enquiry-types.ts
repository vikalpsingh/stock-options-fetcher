export const enquiryStatuses = ["new", "contacted", "sent_to_partner", "converted", "closed", "spam"] as const;
export type EnquiryStatus = (typeof enquiryStatuses)[number];
