"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, BedDouble, BusFront, PackageCheck, Plane, ShieldCheck, TrainFront } from "lucide-react";
import { travelCities } from "@/src/data/travelCities";
import { inferTravelDefaults } from "@/src/lib/travel/defaults";
import { addDays } from "@/src/lib/travel/validation";
import { Button } from "@/components/ui/button";

type Mode = "bus" | "hotel" | "flight" | "train" | "package";

export function TravelSearchWidget({
  sourcePage = "travel-widget",
  campaign = "ujjain-kumbh-2028",
  title = "Plan Your Kumbh Travel",
  defaultFromCity,
  defaultToCity,
  defaultHotelCity,
  defaultFlightToCity,
  packageHref,
}: {
  sourcePage?: string;
  campaign?: string;
  title?: string;
  defaultFromCity?: string;
  defaultToCity?: string;
  defaultHotelCity?: string;
  defaultFlightToCity?: string;
  packageHref?: string;
}) {
  const inferredDefaults = useMemo(() => inferTravelDefaults({ sourcePage, campaign, title }), [sourcePage, campaign, title]);
  const resolvedFromCity = defaultFromCity || inferredDefaults.defaultFromCity;
  const resolvedToCity = defaultToCity || inferredDefaults.defaultToCity;
  const resolvedHotelCity = defaultHotelCity || inferredDefaults.defaultHotelCity;
  const resolvedFlightToCity = defaultFlightToCity || inferredDefaults.defaultFlightToCity;
  const resolvedPackageHref = packageHref || inferredDefaults.packageHref;
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const defaultDate = useMemo(() => addDays(today, 30), [today]);
  const [mode, setMode] = useState<Mode>("hotel");
  const [from, setFrom] = useState(resolvedFromCity);
  const [to, setTo] = useState(resolvedToCity);
  const [hotelCity, setHotelCity] = useState(resolvedHotelCity);
  const [date, setDate] = useState(defaultDate);
  const [checkin, setCheckin] = useState(defaultDate);
  const [checkout, setCheckout] = useState(addDays(defaultDate, 1));
  const [flightTo, setFlightTo] = useState(resolvedFlightToCity);
  const [tripType, setTripType] = useState<"oneway" | "roundtrip">("oneway");
  const [returnDate, setReturnDate] = useState(addDays(defaultDate, 3));
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState(0);
  const [rooms, setRooms] = useState(1);
  const [error, setError] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (mode === "package") {
      window.location.href = `${resolvedPackageHref}?sourcePage=${encodeURIComponent(sourcePage)}#package-enquiry`;
      return;
    }
    if (mode === "hotel" && checkout <= checkin) {
      setError("Checkout must be after check-in.");
      return;
    }
    const sp = new URLSearchParams({ mode, campaign, sourcePage });
    if (mode === "bus") {
      sp.set("from", from); sp.set("to", to); sp.set("date", date);
    }
    if (mode === "hotel") {
      sp.set("city", hotelCity); sp.set("checkin", checkin); sp.set("checkout", checkout); sp.set("adults", String(adults)); sp.set("children", String(children)); sp.set("rooms", String(rooms));
    }
    if (mode === "flight") {
      sp.set("from", from); sp.set("to", flightTo); sp.set("departureDate", date); sp.set("adults", String(adults)); sp.set("children", String(children)); sp.set("tripType", tripType); if (tripType === "roundtrip") sp.set("returnDate", returnDate);
    }
    if (mode === "train") {
      sp.set("from", from); sp.set("to", to); sp.set("date", date);
    }
    const travelUrl = `/go/travel?${sp.toString()}`;
    const opened = window.open(travelUrl, "_blank", "noopener,noreferrer");
    if (!opened) setError("Your browser blocked the new booking window. Please allow pop-ups for IndianKumbh.com and try again.");
  }

  const modeTabs = [
    { id: "bus", label: "Bus", icon: BusFront },
    { id: "hotel", label: "Hotels", icon: BedDouble },
    { id: "flight", label: "Flights", icon: Plane },
    { id: "train", label: "Trains", icon: TrainFront },
    { id: "package", label: "Packages", icon: PackageCheck },
  ] as const;

  return (
    <div className="overflow-hidden rounded-[2rem] border border-gold/35 bg-white shadow-soft">
      <div className="brand-gradient pattern-jaali p-6 text-white sm:p-8">
        <p className="text-xs font-black uppercase tracking-[.2em] text-gold">Travel discovery</p>
        <h2 className="mt-3 font-serif text-3xl text-white sm:text-4xl">{title}</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-orange-50/85">Search partner sites safely after IndianKumbh validates your city, date and passenger details.</p>
      </div>
      <form onSubmit={submit} className="p-5 sm:p-8">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {modeTabs.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setMode(id)} className={`flex min-h-12 items-center justify-center gap-2 rounded-2xl border px-3 text-sm font-bold ${mode === id ? "border-saffron bg-orange-50 text-maroon ring-2 ring-orange-100" : "border-stone-200 text-stone-600"}`}><Icon className="h-4 w-4" />{label}</button>)}
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(mode === "bus" || mode === "flight" || mode === "train") && <CityField label="From city" value={from} onChange={setFrom} />}
          {(mode === "bus" || mode === "train") && <CityField label="To city" value={to} onChange={setTo} />}
          {mode === "flight" && <CityField label="To airport city" value={flightTo} onChange={setFlightTo} />}
          {mode === "hotel" && <CityField label="Hotel city" value={hotelCity} onChange={setHotelCity} />}
          {(mode === "bus" || mode === "flight" || mode === "train") && <Field label={mode === "flight" ? "Departure date" : "Travel date"}><input required type="date" value={date} onChange={(event) => setDate(event.target.value)} className="form-control" /></Field>}
          {mode === "hotel" && <><Field label="Check-in"><input required type="date" value={checkin} onChange={(event) => { setCheckin(event.target.value); if (checkout <= event.target.value) setCheckout(addDays(event.target.value, 1)); }} className="form-control" /></Field><Field label="Checkout"><input required type="date" min={addDays(checkin, 1)} value={checkout} onChange={(event) => setCheckout(event.target.value)} className="form-control" /></Field></>}
          {mode === "flight" && <Field label="Trip type"><select value={tripType} onChange={(event) => setTripType(event.target.value as "oneway" | "roundtrip")} className="form-control"><option value="oneway">One-way</option><option value="roundtrip">Round-trip</option></select></Field>}
          {mode === "flight" && tripType === "roundtrip" && <Field label="Return date"><input required type="date" min={addDays(date, 1)} value={returnDate} onChange={(event) => setReturnDate(event.target.value)} className="form-control" /></Field>}
          {(mode === "hotel" || mode === "flight") && <Field label="Adults"><input min="1" max="30" type="number" value={adults} onChange={(event) => setAdults(Number(event.target.value))} className="form-control" /></Field>}
          {(mode === "hotel" || mode === "flight") && <Field label="Children"><input min="0" max="20" type="number" value={children} onChange={(event) => setChildren(Number(event.target.value))} className="form-control" /></Field>}
          {mode === "hotel" && <Field label="Rooms"><input min="1" max="15" type="number" value={rooms} onChange={(event) => setRooms(Number(event.target.value))} className="form-control" /></Field>}
          {mode === "package" && <><CityField label="Destination" value={resolvedToCity} onChange={() => {}} /><Field label="Package type"><select className="form-control"><option>Family Kumbh Yatra</option><option>Senior Citizen Assisted Yatra</option><option>Indore Stay + Ujjain Day Trip</option></select></Field><div className="text-sm leading-7 text-stone-600">Packages are handled through enquiry. Thrillophilia/local operators can be added after partner verification.</div></>}
        </div>

        {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-800">{error}</p>}
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="submit" size="lg" className="w-full sm:w-auto">{cta(mode)}<ArrowRight className="h-4 w-4" /></Button>
          <Link href="/affiliate-disclosure" className="text-sm font-bold text-maroon underline">How partner links work</Link>
        </div>
        <p className="mt-5 flex gap-2 rounded-2xl bg-amber-50 p-4 text-xs leading-5 text-amber-950"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />Bookings are completed on partner websites. IndianKumbh.com may earn a referral commission at no extra cost to you.</p>
      </form>
    </div>
  );
}

function CityField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <Field label={label}><select value={value} onChange={(event) => onChange(event.target.value)} className="form-control">{travelCities.map((city) => <option key={city.slug} value={city.slug}>{city.cityName}</option>)}</select></Field>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="text-sm font-bold text-ink">{label}{children}</label>;
}

function cta(mode: Mode) {
  if (mode === "bus") return "Search Buses";
  if (mode === "hotel") return "Search Hotels";
  if (mode === "flight") return "Search Flights";
  if (mode === "train") return "Check Trains";
  return "Get Package Quote";
}
