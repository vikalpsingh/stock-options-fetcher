export type PilgrimageStats = {
  slug: string;
  title: string;
  latestKnownStats: { label: string; value: string; sourceType: "official" | "media" | "editorial_estimate"; note: string }[];
  planningTakeaways: string[];
  confidenceLevel: "high" | "medium" | "low";
};

export const pilgrimageStats: PilgrimageStats[] = [
  {
    slug: "char-dham-yatra",
    title: "Char Dham Yatra travel scale",
    latestKnownStats: [
      { label: "Annual yatra numbers", value: "Varies by year", sourceType: "editorial_estimate", note: "Do not publish exact numbers without official source verification." },
      { label: "Registration", value: "Required through official channels", sourceType: "official", note: "Verify the current Uttarakhand process before travel." },
    ],
    planningTakeaways: ["Peak crowd is usually around opening weeks, summer vacation, long weekends and pre/post-monsoon windows.", "Weather and landslide risk can affect road movement.", "Health planning is essential for Kedarnath and Yamunotri."],
    confidenceLevel: "medium",
  },
  {
    slug: "12-jyotirlinga",
    title: "12 Jyotirlinga travel scale",
    latestKnownStats: [
      { label: "Visitor traffic", value: "Distributed across the year", sourceType: "editorial_estimate", note: "Demand spikes during Maha Shivratri, Shravan/Sawan, Mondays, weekends and local festivals." },
      { label: "Planning pattern", value: "1-site, 2-site, regional circuit or complete yatra", sourceType: "editorial_estimate", note: "Regional circuits are more practical for families and seniors." },
    ],
    planningTakeaways: ["Mahakaleshwar, Kashi Vishwanath, Kedarnath, Somnath, Trimbakeshwar and Rameshwaram can see high seasonal demand.", "Avoid a rushed all-India plan unless medically and logistically prepared."],
    confidenceLevel: "medium",
  },
];

export function getPilgrimageStats(slug: string) {
  return pilgrimageStats.find((item) => item.slug === slug);
}
