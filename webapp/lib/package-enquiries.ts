import "server-only";

import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { enquiryStatuses, type EnquiryStatus } from "./package-enquiry-types";

export { enquiryStatuses, type EnquiryStatus } from "./package-enquiry-types";

export type PackageEnquiryInput = {
  fullName: string;
  mobile: string;
  whatsappNumber: string;
  email: string;
  sourceCity: string;
  travelMonth: string;
  numberOfAdults: number;
  numberOfChildren: number;
  hasSeniorCitizens: boolean;
  budgetPerPerson: string;
  stayPreference: "Ujjain" | "Indore" | "Bhopal" | "Not Sure";
  packageType: string;
  needMahakalDarshanSupport: boolean;
  needTransport: boolean;
  message: string;
  consentAccepted: boolean;
  honeypot: string;
  sourcePage: string;
  utmSource: string;
  utmMedium: string;
  utmCampaign: string;
};

export type PackageEnquiry = Omit<PackageEnquiryInput, "honeypot"> & {
  id: string;
  createdAt: string;
  status: EnquiryStatus;
  assignedPartnerId: string | null;
  userAgent: string;
};

export type AffiliateClick = {
  id: string;
  linkId: string;
  providerId: string;
  destination: string;
  campaign: string;
  sourcePage: string;
  createdAt: string;
  userAgent: string;
  referrer: string;
};

const dataDirectory = path.join(process.cwd(), "data");
const enquiryFile = path.join(dataDirectory, "package-enquiries.json");
const clickFile = path.join(dataDirectory, "affiliate-clicks.json");

let enquiryWriteQueue: Promise<unknown> = Promise.resolve();
let clickWriteQueue: Promise<unknown> = Promise.resolve();

export function normalizeIndianMobile(value: string) {
  const digits = value.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) return digits.slice(2);
  if (digits.length === 11 && digits.startsWith("0")) return digits.slice(1);
  return digits;
}

export function isValidIndianMobile(value: string) {
  return /^[6-9]\d{9}$/.test(normalizeIndianMobile(value));
}

export function validatePackageEnquiry(body: unknown):
  | { success: true; data: PackageEnquiryInput }
  | { success: false; error: string } {
  if (!body || typeof body !== "object") return { success: false, error: "Please submit the enquiry form again." };
  const input = body as Record<string, unknown>;
  const text = (key: string, max = 500) => typeof input[key] === "string" ? input[key].trim().slice(0, max) : "";
  const bool = (key: string) => input[key] === true;
  const number = (key: string, fallback = 0) => {
    const value = Number(input[key]);
    return Number.isFinite(value) ? Math.max(0, Math.floor(value)) : fallback;
  };

  if (text("honeypot")) return { success: false, error: "Your enquiry could not be submitted." };
  if (text("fullName", 120).length < 2) return { success: false, error: "Please enter your full name." };
  if (!isValidIndianMobile(text("mobile", 20))) return { success: false, error: "Please enter a valid 10-digit Indian mobile number." };
  if (!text("sourceCity", 100)) return { success: false, error: "Please enter your starting city." };
  if (!text("packageType", 120)) return { success: false, error: "Please select a package type." };
  if (!bool("consentAccepted")) return { success: false, error: "Please accept the consent statement before submitting." };

  const stayPreference = text("stayPreference", 20);
  const allowedStays = ["Ujjain", "Indore", "Bhopal", "Not Sure"] as const;

  return {
    success: true,
    data: {
      fullName: text("fullName", 120),
      mobile: normalizeIndianMobile(text("mobile", 20)),
      whatsappNumber: text("whatsappNumber", 20) ? normalizeIndianMobile(text("whatsappNumber", 20)) : "",
      email: text("email", 180),
      sourceCity: text("sourceCity", 100),
      travelMonth: text("travelMonth", 20),
      numberOfAdults: Math.min(number("numberOfAdults", 1), 100),
      numberOfChildren: Math.min(number("numberOfChildren"), 100),
      hasSeniorCitizens: bool("hasSeniorCitizens"),
      budgetPerPerson: text("budgetPerPerson", 60),
      stayPreference: allowedStays.includes(stayPreference as (typeof allowedStays)[number]) ? stayPreference as PackageEnquiryInput["stayPreference"] : "Not Sure",
      packageType: text("packageType", 120),
      needMahakalDarshanSupport: bool("needMahakalDarshanSupport"),
      needTransport: bool("needTransport"),
      message: text("message", 1000),
      consentAccepted: true,
      honeypot: "",
      sourcePage: text("sourcePage", 300) || "/ujjain-kumbh-2028/packages",
      utmSource: text("utmSource", 100),
      utmMedium: text("utmMedium", 100),
      utmCampaign: text("utmCampaign", 100),
    },
  };
}

export async function createPackageEnquiry(input: PackageEnquiryInput, userAgent: string) {
  return queueEnquiryWrite(async (): Promise<{ duplicate: boolean; enquiry: PackageEnquiry }> => {
    const current = await readJsonArray<PackageEnquiry>(enquiryFile);
    const duplicateWindow = Date.now() - 10 * 60 * 1000;
    const duplicate = current.find(
      (item) => item.mobile === input.mobile && item.packageType === input.packageType && Date.parse(item.createdAt) >= duplicateWindow,
    );
    if (duplicate) {
      return { duplicate: true, enquiry: duplicate };
    }
    const { honeypot: _honeypot, ...safeInput } = input;
    const enquiry: PackageEnquiry = {
      ...safeInput,
      id: randomUUID(),
      createdAt: new Date().toISOString(),
      status: "new",
      assignedPartnerId: null,
      userAgent: userAgent.slice(0, 500),
    };
    await writeJsonAtomic(enquiryFile, [...current, enquiry]);
    return { duplicate: false, enquiry };
  });
}

export async function getPackageEnquiries() {
  return readJsonArray<PackageEnquiry>(enquiryFile);
}

export async function updatePackageEnquiry(id: string, updates: { status?: EnquiryStatus; assignedPartnerId?: string | null }) {
  let updated: PackageEnquiry | null = null;
  await queueEnquiryWrite(async () => {
    const enquiries = await readJsonArray<PackageEnquiry>(enquiryFile);
    const next = enquiries.map((item) => {
      if (item.id !== id) return item;
      updated = { ...item, ...updates };
      return updated;
    });
    if (!updated) throw new Error("Enquiry not found");
    await writeJsonAtomic(enquiryFile, next);
  });
  return updated;
}

export async function logAffiliateClick(click: Omit<AffiliateClick, "id" | "createdAt">) {
  const record: AffiliateClick = { ...click, id: randomUUID(), createdAt: new Date().toISOString() };
  await queueClickWrite(async () => {
    const current = await readJsonArray<AffiliateClick>(clickFile);
    await writeJsonAtomic(clickFile, [...current, record].slice(-10000));
  });
  return record;
}

async function readJsonArray<T>(file: string): Promise<T[]> {
  try {
    const content = await readFile(file, "utf8");
    const parsed = JSON.parse(content);
    return Array.isArray(parsed) ? parsed as T[] : [];
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

async function writeJsonAtomic(file: string, data: unknown[]) {
  await mkdir(dataDirectory, { recursive: true });
  const temporary = `${file}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  await rename(temporary, file);
}

function queueEnquiryWrite<T>(operation: () => Promise<T>) {
  const result = enquiryWriteQueue.then(operation, operation);
  enquiryWriteQueue = result.then(() => undefined, () => undefined);
  return result;
}

function queueClickWrite<T>(operation: () => Promise<T>) {
  const result = clickWriteQueue.then(operation, operation);
  clickWriteQueue = result.then(() => undefined, () => undefined);
  return result;
}
