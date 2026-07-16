import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

const dataDirectory = path.join(process.cwd(), "data");
const outboundClicksFile = path.join(dataDirectory, "outbound-clicks.json");

export type TravelOutboundClick = {
  id: string;
  createdAt: string;
  mode: string;
  providerId: string;
  fromCitySlug?: string;
  toCitySlug?: string;
  citySlug?: string;
  date?: string;
  checkin?: string;
  checkout?: string;
  departureDate?: string;
  campaign?: string;
  sourcePage?: string;
  userAgent: string;
  referrer: string;
  targetHost: string;
};

export async function getTravelOutboundClicks() {
  try {
    const clicks = JSON.parse(await fs.readFile(outboundClicksFile, "utf8")) as TravelOutboundClick[];
    return Array.isArray(clicks) ? clicks : [];
  } catch {
    return [];
  }
}

export async function logTravelOutboundClick(click: TravelOutboundClick) {
  await fs.mkdir(dataDirectory, { recursive: true });
  const clicks = await getTravelOutboundClicks();
  clicks.push(click);
  await fs.writeFile(outboundClicksFile, `${JSON.stringify(clicks, null, 2)}\n`, "utf8");
}

export function toTravelClicksCsv(clicks: TravelOutboundClick[]) {
  const headers = ["createdAt", "mode", "providerId", "fromCitySlug", "toCitySlug", "citySlug", "date", "checkin", "checkout", "departureDate", "campaign", "sourcePage", "targetHost", "referrer"];
  return [headers.join(","), ...clicks.map((item) => headers.map((header) => csvCell(item[header as keyof TravelOutboundClick])).join(","))].join("\r\n");
}

function csvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll("\"", "\"\"")}"`;
}
