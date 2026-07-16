import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function transpileTs(path) {
  return ts.transpileModule(fs.readFileSync(path, "utf8"), {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: path,
  }).outputText;
}

function runModule(path, requireShim) {
  const module = { exports: {} };
  vm.runInNewContext(transpileTs(path), {
    console,
    exports: module.exports,
    module,
    require: requireShim,
    process,
    URL,
    Date,
  });
  return module.exports;
}

function loadBookingModule() {
  const hotelCitiesModule = runModule("src/data/hotelCities.ts", (id) => {
    throw new Error(`Unexpected hotelCities require: ${id}`);
  });
  return runModule("src/lib/buildBookingUrl.ts", (id) => {
    if (id === "@/src/data/hotelCities") return hotelCitiesModule;
    throw new Error(`Unexpected bookingUrl require: ${id}`);
  });
}

const { buildBookingSearchUrl } = loadBookingModule();

test("buildBookingSearchUrl creates a clean Booking.com URL with affiliate label", () => {
  process.env.BOOKING_AFFILIATE_ID = "123456";

  const url = new URL(buildBookingSearchUrl({
    citySlug: "ujjain",
    checkin: "2026-07-15",
    checkout: "2026-07-16",
    adults: 2,
    rooms: 1,
    children: 0,
    budget: "standard",
    campaign: "ujjain-kumbh-2028",
    sourcePage: "home",
  }));

  assert.equal(url.hostname, "www.booking.com");
  assert.equal(url.pathname, "/searchresults.html");
  assert.equal(url.searchParams.get("ss"), "Ujjain, Madhya Pradesh, India");
  assert.equal(url.searchParams.get("checkin"), "2026-07-15");
  assert.equal(url.searchParams.get("checkout"), "2026-07-16");
  assert.equal(url.searchParams.get("group_adults"), "2");
  assert.equal(url.searchParams.get("no_rooms"), "1");
  assert.equal(url.searchParams.get("group_children"), "0");
  assert.equal(url.searchParams.get("aid"), "123456");
  assert.equal(url.searchParams.get("label"), "indiankumbh-ujjain-kumbh-2028-ujjain-standard-home");
  assert.equal(url.searchParams.has("destinationCity"), false);
  assert.equal(url.searchParams.has("travellersCount"), false);
  assert.equal(url.searchParams.has("chal_t"), false);
  assert.equal(url.searchParams.has("force_referer"), false);
  assert.equal(url.toString().includes("undefined"), false);
});

test("buildBookingSearchUrl adjusts checkout after checkin using city default nights", () => {
  const url = new URL(buildBookingSearchUrl({
    citySlug: "indore",
    checkin: "2026-07-15",
    checkout: "2026-07-15",
    campaign: "family-trip",
  }));

  assert.equal(url.searchParams.get("ss"), "Indore, Madhya Pradesh, India");
  assert.equal(url.searchParams.get("checkin"), "2026-07-15");
  assert.equal(url.searchParams.get("checkout"), "2026-07-17");
  assert.equal(url.searchParams.get("group_adults"), "2");
  assert.equal(url.searchParams.get("no_rooms"), "1");
});

test("buildBookingSearchUrl rejects unknown city and invalid dates", () => {
  assert.throws(() => buildBookingSearchUrl({ citySlug: "unknown", checkin: "2026-07-15", checkout: "2026-07-16" }), /invalid-city/);
  assert.throws(() => buildBookingSearchUrl({ citySlug: "ujjain", checkin: "15-07-2026", checkout: "2026-07-16" }), /invalid-checkin/);
  assert.throws(() => buildBookingSearchUrl({ citySlug: "ujjain", checkin: "2026-07-15", checkout: "2026-02-31" }), /invalid-checkout/);
});
