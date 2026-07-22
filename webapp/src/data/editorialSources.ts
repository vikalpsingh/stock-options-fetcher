export type EditorialSource = {
  id: string;
  title: string;
  sourceType: "official" | "government" | "temple" | "media" | "travel_partner" | "editorial";
  url: string;
  lastChecked: string;
  reliability: "high" | "medium" | "low";
  notes: string;
};

export const editorialSources: EditorialSource[] = [
  { id: "nashik-kumbh-editorial", title: "Nashik Kumbh editorial planning note", sourceType: "editorial", url: "/kumbh-mela/nashik-kumbh-2027", lastChecked: "2026-07-15", reliability: "medium", notes: "Use official Maharashtra government, Nashik district and temple sources before publishing final dates, routes and service locations." },
  { id: "ujjain-kumbh-editorial", title: "Ujjain Kumbh editorial planning note", sourceType: "editorial", url: "/kumbh-mela/ujjain-kumbh-2028", lastChecked: "2026-07-15", reliability: "medium", notes: "Use official Madhya Pradesh government, Ujjain district and Mahakal temple sources before publishing final dates, routes and service locations." },
];

export function getEditorialSource(id?: string) {
  if (!id) return undefined;
  return editorialSources.find((source) => source.id === id);
}
