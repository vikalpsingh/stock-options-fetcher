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
  "@/src/lib/travel/defaults": "src/lib/travel/defaults.ts",
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
const { inferTravelDefaults } = load("src/lib/travel/defaults.ts");

function assertSafePartnerUrl(url) {
  for (const badToken of ["undefined", "null", "NaN", "[object Object]"]) {
    assert.equal(url.includes(badToken), false, `URL must not contain ${badToken}: ${url}`);
  }
}

test("generic hotel redirect builds a clean Booking.com URL", () => {
  const result = buildTravelUrl({ mode: "hotel", citySlug: "indore", checkin: "2026-07-15", checkout: "2026-07-15", adults: 2, rooms: 1, campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "booking");
  assert.equal(url.hostname, "www.booking.com");
  assert.equal(url.searchParams.get("ss"), "Indore, Madhya Pradesh, India");
  assert.equal(url.searchParams.get("checkout"), "2026-07-16");
  assert.equal(result.url.includes("undefined"), false);
  assert.equal(result.url.includes("chal_t"), false);
  assertSafePartnerUrl(result.url);
});

test("generic flight redirect uses airport codes and configured primary provider", () => {
  const result = buildTravelUrl({ mode: "flight", fromCitySlug: "bengaluru", toCitySlug: "indore", departureDate: "2026-07-13", adults: 2, campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "easemytrip_flights");
  assert.equal(url.hostname, "www.easemytrip.com");
  assert.equal(url.searchParams.get("from"), "BLR");
  assert.equal(url.searchParams.get("to"), "IDR");
  assertSafePartnerUrl(result.url);
});

test("generic train redirect is reference-only and safe", () => {
  const result = buildTravelUrl({ mode: "train", fromCitySlug: "mumbai", toCitySlug: "ujjain", date: "2026-07-13", campaign: "ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "irctc_tourism");
  assert.equal(url.hostname, "www.irctctourism.com");
  assert.equal(url.searchParams.get("from"), "MMCT");
  assert.equal(url.searchParams.get("to"), "UJN");
  assertSafePartnerUrl(result.url);
});

test("generic bus redirect refuses unverified RedBus city IDs", () => {
  assert.throws(() => buildTravelUrl({ mode: "bus", fromCitySlug: "bengaluru", toCitySlug: "ujjain", date: "2026-07-13" }), /redbus-city-id-unverified/);
});

test("Nashik hotel redirect opens Booking.com with Nashik destination values", () => {
  const result = buildTravelUrl({ mode: "hotel", citySlug: "nashik", checkin: "2027-08-01", checkout: "2027-08-03", adults: 2, rooms: 1, campaign: "nashik-kumbh-2027", sourcePage: "kumbh-nashik-kumbh-2027" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "booking");
  assert.equal(url.hostname, "www.booking.com");
  assert.equal(url.searchParams.get("ss"), "Nashik, Maharashtra, India");
  assert.equal(url.searchParams.get("checkin"), "2027-08-01");
  assert.equal(url.searchParams.get("checkout"), "2027-08-03");
  assert.equal(url.searchParams.get("group_adults"), "2");
  assertSafePartnerUrl(result.url);
});

test("Nashik flight redirect uses Nashik airport code and safe campaign values", () => {
  const result = buildTravelUrl({ mode: "flight", fromCitySlug: "pune", toCitySlug: "nashik", departureDate: "2027-08-01", adults: 2, campaign: "nashik-kumbh-2027", sourcePage: "kumbh-nashik-kumbh-2027" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "easemytrip_flights");
  assert.equal(url.hostname, "www.easemytrip.com");
  assert.equal(url.searchParams.get("from"), "PNQ");
  assert.equal(url.searchParams.get("to"), "ISK");
  assert.equal(url.searchParams.get("date"), "2027-08-01");
  assertSafePartnerUrl(result.url);
});

test("Nashik train redirect uses Nashik railway station and safe values", () => {
  const result = buildTravelUrl({ mode: "train", fromCitySlug: "mumbai", toCitySlug: "nashik", date: "2027-08-01", campaign: "nashik-kumbh-2027", sourcePage: "kumbh-nashik-kumbh-2027" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "irctc_tourism");
  assert.equal(url.hostname, "www.irctctourism.com");
  assert.equal(url.searchParams.get("from"), "MMCT");
  assert.equal(url.searchParams.get("to"), "NK");
  assertSafePartnerUrl(result.url);
});

test("Nashik bus redirect fails safely until RedBus city IDs are verified", () => {
  assert.throws(() => buildTravelUrl({ mode: "bus", fromCitySlug: "pune", toCitySlug: "nashik", date: "2027-08-01", campaign: "nashik-kumbh-2027" }), /redbus-city-id-unverified/);
});

test("travel widget defaults infer the current Kumbh city from page context", () => {
  assert.equal(JSON.stringify(inferTravelDefaults({ sourcePage: "kumbh-nashik-kumbh-2027", campaign: "nashik-kumbh-2027", title: "Plan travel" })), JSON.stringify({
    defaultFromCity: "pune",
    defaultToCity: "nashik",
    defaultHotelCity: "nashik",
    defaultFlightToCity: "nashik",
    packageHref: "/kumbh-mela/nashik-kumbh-2027/packages",
  }));
  assert.equal(JSON.stringify(inferTravelDefaults({ sourcePage: "kumbh-ujjain-kumbh-2028", campaign: "ujjain-kumbh-2028", title: "Plan travel" })), JSON.stringify({
    defaultFromCity: "bengaluru",
    defaultToCity: "ujjain",
    defaultHotelCity: "ujjain",
    defaultFlightToCity: "ujjain",
    packageHref: "/kumbh-mela/ujjain-kumbh-2028/packages",
  }));
  assert.equal(inferTravelDefaults({ sourcePage: "kumbh-prayagraj-kumbh", campaign: "prayagraj-kumbh", title: "Search travel" }).defaultToCity, "prayagraj");
  assert.equal(inferTravelDefaults({ sourcePage: "kumbh-haridwar-kumbh", campaign: "haridwar-kumbh", title: "Search travel" }).defaultToCity, "haridwar");
});

test("Ujjain current-city flight default maps safely to Indore airport code", () => {
  const result = buildTravelUrl({ mode: "flight", fromCitySlug: "bengaluru", toCitySlug: "ujjain", departureDate: "2028-04-01", adults: 2, campaign: "ujjain-kumbh-2028", sourcePage: "kumbh-ujjain-kumbh-2028" });
  const url = new URL(result.url);
  assert.equal(result.providerId, "easemytrip_flights");
  assert.equal(url.searchParams.get("from"), "BLR");
  assert.equal(url.searchParams.get("to"), "IDR");
  assertSafePartnerUrl(result.url);
});
