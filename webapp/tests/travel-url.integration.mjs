import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const moduleById = {
  "@/src/data/travelProviders": "src/data/travelProviders.ts",
  "@/src/data/travelModeConfig": "src/data/travelModeConfig.ts",
  "@/src/data/travelCities": "src/data/travelCities.ts",
  "@/src/lib/travel/buildTravelUrl": "src/lib/travel/buildTravelUrl.ts",
  "@/src/lib/travel/buildBookingUrl": "src/lib/travel/buildBookingUrl.ts",
  "@/src/lib/travel/buildFlightUrl": "src/lib/travel/buildFlightUrl.ts",
  "@/src/lib/travel/buildTrainUrl": "src/lib/travel/buildTrainUrl.ts",
  "@/src/lib/travel/buildRedbusUrl": "src/lib/travel/buildRedbusUrl.ts",
  "@/src/lib/travel/campaign": "src/lib/travel/campaign.ts",
  "@/src/lib/travel/validation": "src/lib/travel/validation.ts",
};
const cache = new Map();

function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const source = fs.readFileSync(file, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { esModuleInterop: true, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: file,
  }).outputText;
  const module = { exports: {} };
  cache.set(file, module);
  const requireShim = (id) => {
    if (moduleById[id]) return load(moduleById[id]);
    if (id.startsWith(".")) return load(path.normalize(path.join(path.dirname(file), `${id}.ts`)));
    throw new Error(`Unexpected require: ${id} from ${file}`);
  };
  vm.runInNewContext(compiled, { console, exports: module.exports, module, require: requireShim, process, URL, Date });
  return module.exports;
}

const { buildTravelUrl } = load("src/lib/travel/buildTravelUrl.ts");

test("generic hotel redirect builds a clean Booking.com URL", () => {
  const result = buildTravelUrl({ mode: "hotel", citySlug: "indore", checkin: "2026-07-15", checkout: "2026-07-15", adults: 2, rooms: 1, campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "booking");
  assert.equal(url.hostname, "www.booking.com");
  assert.equal(url.searchParams.get("ss"), "Indore, Madhya Pradesh, India");
  assert.equal(url.searchParams.get("checkout"), "2026-07-16");
  assert.equal(result.url.includes("undefined"), false);
  assert.equal(result.url.includes("chal_t"), false);
});

test("generic flight redirect uses airport codes and configured primary provider", () => {
  const result = buildTravelUrl({ mode: "flight", fromCitySlug: "bengaluru", toCitySlug: "indore", departureDate: "2026-07-13", adults: 2, campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "easemytrip_flights");
  assert.equal(url.hostname, "www.easemytrip.com");
  assert.equal(url.searchParams.get("from"), "BLR");
  assert.equal(url.searchParams.get("to"), "IDR");
});

test("generic train redirect is reference-only and safe", () => {
  const result = buildTravelUrl({ mode: "train", fromCitySlug: "mumbai", toCitySlug: "ujjain", date: "2026-07-13", campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "irctc_tourism");
  assert.equal(url.hostname, "www.irctctourism.com");
  assert.equal(url.searchParams.get("from"), "MMCT");
  assert.equal(url.searchParams.get("to"), "UJN");
});

test("generic bus redirect refuses unverified RedBus city IDs", () => {
  assert.throws(() => buildTravelUrl({ mode: "bus", fromCitySlug: "bengaluru", toCitySlug: "ujjain", date: "2026-07-13" }), /redbus-city-id-unverified/);
});
