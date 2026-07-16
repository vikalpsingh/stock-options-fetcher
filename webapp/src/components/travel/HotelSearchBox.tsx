"use client";

import { FormEvent, useMemo, useState } from "react";
import { ArrowRight, BedDouble, CalendarDays, Hotel, ShieldCheck, Users } from "lucide-react";
import { hotelCities } from "@/src/data/hotelCities";
import { addDays, getDefaultHotelDates, type BookingBudget } from "@/src/lib/buildBookingUrl";
import { Button } from "@/components/ui/button";

type HotelSearchBoxProps = {
  title?: string;
  campaign?: string;
  sourcePage?: string;
  defaultCity?: string;
};

export function HotelSearchBox({
  title = "Search hotels for your Kumbh trip",
  campaign = "ujjain-kumbh-2028",
  sourcePage = "hotel-search-box",
  defaultCity = "ujjain",
}: HotelSearchBoxProps) {
  const defaults = useMemo(() => getDefaultHotelDates(defaultCity), [defaultCity]);
  const [city, setCity] = useState(defaultCity);
  const [checkin, setCheckin] = useState(defaults.checkin);
  const [checkout, setCheckout] = useState(defaults.checkout);
  const [adults, setAdults] = useState(2);
  const [rooms, setRooms] = useState(1);
  const [children, setChildren] = useState(0);
  const [budget, setBudget] = useState<BookingBudget>("standard");
  const [error, setError] = useState("");

  function selectCity(slug: string) {
    setCity(slug);
    const dates = getDefaultHotelDates(slug);
    setCheckin(dates.checkin);
    setCheckout(dates.checkout);
  }

  function updateCheckin(value: string) {
    setCheckin(value);
    if (checkout <= value) setCheckout(addDays(value, 1));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (checkout <= checkin) {
      setError("Checkout date must be after check-in date.");
      return;
    }
    if (adults < 1 || rooms < 1) {
      setError("Adults and rooms must be at least 1.");
      return;
    }
    setError("");
    const query = new URLSearchParams({
      city,
      checkin,
      checkout,
      adults: String(adults),
      rooms: String(rooms),
      children: String(Math.max(0, children)),
      budget,
      campaign,
      sourcePage,
    });
    window.location.href = `/go/booking?${query.toString()}`;
  }

  return (
    <form onSubmit={submit} className="overflow-hidden rounded-[2rem] border border-gold/35 bg-white shadow-soft">
      <div className="brand-gradient pattern-jaali p-6 text-white sm:p-8">
        <p className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[.2em] text-gold"><Hotel className="h-4 w-4" />Booking.com hotel search</p>
        <h3 className="mt-3 font-serif text-3xl text-white sm:text-4xl">{title}</h3>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-orange-50/85">Hotel booking is completed on Booking.com. IndianKumbh.com may earn a referral commission at no extra cost to you.</p>
      </div>

      <div className="space-y-5 p-5 sm:p-8">
        <div>
          <p className="text-sm font-bold text-ink">Quick city choice</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {["ujjain", "indore", "bhopal"].map((slug) => (
              <button key={slug} type="button" onClick={() => selectCity(slug)} className={`rounded-full border px-4 py-2 text-sm font-bold transition ${city === slug ? "border-saffron bg-orange-50 text-maroon ring-2 ring-orange-100" : "border-stone-200 bg-white text-stone-600 hover:border-gold"}`}>
                {hotelCities.find((item) => item.slug === slug)?.cityName}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="City">
            <select value={city} onChange={(event) => selectCity(event.target.value)} className="form-control">
              {hotelCities.map((item) => <option key={item.slug} value={item.slug}>{item.cityName}</option>)}
            </select>
          </Field>
          <Field label="Check-in">
            <input required type="date" value={checkin} onChange={(event) => updateCheckin(event.target.value)} className="form-control" />
          </Field>
          <Field label="Checkout">
            <input required type="date" min={addDays(checkin, 1)} value={checkout} onChange={(event) => setCheckout(event.target.value)} className="form-control" />
          </Field>
          <Field label="Adults">
            <input required type="number" min="1" max="30" value={adults} onChange={(event) => setAdults(Number(event.target.value))} className="form-control" />
          </Field>
          <Field label="Rooms">
            <input required type="number" min="1" max="15" value={rooms} onChange={(event) => setRooms(Number(event.target.value))} className="form-control" />
          </Field>
          <Field label="Children">
            <input type="number" min="0" max="20" value={children} onChange={(event) => setChildren(Number(event.target.value))} className="form-control" />
          </Field>
          <Field label="Budget" className="sm:col-span-2 lg:col-span-1">
            <select value={budget} onChange={(event) => setBudget(event.target.value as BookingBudget)} className="form-control">
              <option value="budget">Budget</option>
              <option value="standard">Standard</option>
              <option value="premium">Premium</option>
            </select>
          </Field>
          <div className="flex items-end sm:col-span-2">
            <Button type="submit" size="lg" className="w-full">
              Check hotels on Booking.com <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {error && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">{error}</p>}
        <div className="grid gap-3 text-sm leading-6 text-stone-600 md:grid-cols-3">
          <p className="flex gap-2"><BedDouble className="mt-1 h-4 w-4 shrink-0 text-saffron" />Indore hotels usually convert best for family comfort and airport access.</p>
          <p className="flex gap-2"><CalendarDays className="mt-1 h-4 w-4 shrink-0 text-saffron" />Ujjain is high intent, but rooms may be limited during Kumbh dates.</p>
          <p className="flex gap-2"><Users className="mt-1 h-4 w-4 shrink-0 text-saffron" />Bhopal works for extended MP trips and heritage add-ons.</p>
        </div>
        <p className="flex gap-2 rounded-2xl bg-amber-50 p-4 text-xs leading-5 text-amber-950"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />Sponsored / affiliate link. Booking completed on partner website.</p>
      </div>
    </form>
  );
}

function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return <label className={`text-sm font-bold text-ink ${className}`}>{label}{children}</label>;
}
