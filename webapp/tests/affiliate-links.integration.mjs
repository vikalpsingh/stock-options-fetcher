import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function loadAffiliateLinkModule() {
  const source = fs.readFileSync("lib/affiliate-links.ts", "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: "lib/affiliate-links.ts",
  }).outputText;

  const module = { exports: {} };
  const requireShim = (id) => {
    if (id === "./trip-planner") return {};
    throw new Error(`Unexpected test require: ${id}`);
  };

  vm.runInNewContext(compiled, {
    console,
    exports: module.exports,
    module,
    require: requireShim,
    URL,
    URLSearchParams,
  });

  return module.exports;
}

const { generateAffiliateLinks } = loadAffiliateLinkModule();

const screenshotInput = {
  fromCity: "Bangalore",
  travelDate: "2026-07-14",
  returnDate: "2026-07-18",
  travellersCount: 2,
  hasSeniorCitizens: true,
  travelMode: "not_sure",
  stayCityPreference: "not_sure",
  budget: "standard",
  needsDarshanHelp: true,
  needsLocalTransport: true,
};

const ujjainRecommendation = {
  stayCity: "Ujjain",
  stayReason: "Ujjain keeps Mahakal darshan close.",
  routeSuggestion: "Compare direct train and bus options.",
  crowdPlanningNote: "Keep buffer time.",
  practicalActions: [],
  destinationCity: "Ujjain",
};

test("RedBus link overwrites undefined template values with selected trip data", () => {
  const configuredTemplate =
    "https://www.redbus.in/search?fromCityId=undefined&fromCityName=undefined&toCityId=undefined&toCityName=undefined&onward=13-Jul-2026&doj=13-Jul-2026&ref=search";

  const links = generateAffiliateLinks(screenshotInput, ujjainRecommendation, {
    travelBaseUrl: configuredTemplate,
    hotelBaseUrl: "https://www.booking.com/searchresults.html",
  });

  const url = new URL(links.travelUrl);

  assert.equal(url.hostname, "www.redbus.in");
  assert.equal(url.pathname, "/search");
  assert.equal(url.searchParams.get("fromCityName"), "Bangalore");
  assert.equal(url.searchParams.get("toCityName"), "Ujjain");
  assert.equal(url.searchParams.get("src"), "Bangalore");
  assert.equal(url.searchParams.get("dst"), "Ujjain");
  assert.equal(url.searchParams.get("onward"), "14-Jul-2026");
  assert.equal(url.searchParams.get("doj"), "14-Jul-2026");
  assert.equal(url.searchParams.get("travellersCount"), "2");
  assert.equal(url.searchParams.get("ref"), "search");
  assert.equal(url.searchParams.has("fromCityId"), false);
  assert.equal(url.searchParams.has("toCityId"), false);
  assert.equal(links.travelUrl.includes("undefined"), false);
});

test("non-RedBus travel partners continue to receive generic trip parameters", () => {
  const links = generateAffiliateLinks(screenshotInput, ujjainRecommendation, {
    travelBaseUrl: "https://partner.example/search",
    hotelBaseUrl: "https://www.booking.com/searchresults.html",
  });

  const url = new URL(links.travelUrl);

  assert.equal(url.searchParams.get("fromCity"), "Bangalore");
  assert.equal(url.searchParams.get("destinationCity"), "Ujjain");
  assert.equal(url.searchParams.get("travelDate"), "2026-07-14");
  assert.equal(url.searchParams.get("returnDate"), "2026-07-18");
  assert.equal(url.searchParams.get("travellersCount"), "2");
  assert.equal(url.searchParams.get("travelMode"), "not_sure");
});

test("Booking.com hotel buttons use internal tracked redirect instead of direct external links", () => {
  const sameDayHotelInput = {
    ...screenshotInput,
    travelDate: "2026-07-15",
    returnDate: "2026-07-15",
  };
  const configuredTemplate =
    "https://www.booking.com/searchresults.html?destinationCity=Ujjain&checkin=2026-07-15&checkout=2026-07-15&travellersCount=2&budget=standard&chal_t=1783877664081&force_referer=";

  const links = generateAffiliateLinks(sameDayHotelInput, ujjainRecommendation, {
    travelBaseUrl: "https://www.redbus.in/search",
    hotelBaseUrl: configuredTemplate,
  });

  const url = new URL(links.hotelUrl, "https://indiankumbh.com");

  assert.equal(url.hostname, "indiankumbh.com");
  assert.equal(url.pathname, "/go/booking");
  assert.equal(url.searchParams.get("city"), "ujjain");
  assert.equal(url.searchParams.get("checkin"), "2026-07-15");
  assert.equal(url.searchParams.get("checkout"), "2026-07-16");
  assert.equal(url.searchParams.get("adults"), "2");
  assert.equal(url.searchParams.get("rooms"), "1");
  assert.equal(url.searchParams.get("children"), "0");
  assert.equal(url.searchParams.get("budget"), "standard");
  assert.equal(url.searchParams.get("campaign"), "plan-and-book");
  assert.equal(url.searchParams.get("sourcePage"), "plan-and-book");
  assert.equal(url.searchParams.has("destinationCity"), false);
  assert.equal(url.searchParams.has("travellersCount"), false);
  assert.equal(url.searchParams.has("chal_t"), false);
  assert.equal(url.searchParams.has("force_referer"), false);
});

test("non-Booking hotel partners continue to receive generic hotel parameters", () => {
  const links = generateAffiliateLinks(screenshotInput, ujjainRecommendation, {
    travelBaseUrl: "https://www.redbus.in/search",
    hotelBaseUrl: "https://hotel-partner.example/search",
  });

  const url = new URL(links.hotelUrl);

  assert.equal(url.searchParams.get("destinationCity"), "Ujjain");
  assert.equal(url.searchParams.get("checkin"), "2026-07-14");
  assert.equal(url.searchParams.get("checkout"), "2026-07-18");
  assert.equal(url.searchParams.get("travellersCount"), "2");
  assert.equal(url.searchParams.get("budget"), "standard");
});
