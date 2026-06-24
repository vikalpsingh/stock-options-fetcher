"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  BedDouble,
  BusFront,
  Check,
  ExternalLink,
  HeartHandshake,
  Hotel,
  Landmark,
  MapPin,
  Route,
  ShieldCheck,
  Sparkles,
  TicketCheck,
  Users,
} from "lucide-react";
import { trackPlannerEvent } from "@/lib/analytics";
import { generateAffiliateLinks, type AffiliateLinkConfig } from "@/lib/affiliate-links";
import { feedbackOptions, saveTripFeedback, saveTripSubmission, type FeedbackOption } from "@/lib/feedback";
import {
  budgetLevels,
  generateTripRecommendation,
  stayCities,
  travelModes,
  type TripPlannerInput,
  type TripRecommendation,
} from "@/lib/trip-planner";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

type ResultState = {
  input: TripPlannerInput;
  recommendation: TripRecommendation;
  links: ReturnType<typeof generateAffiliateLinks>;
  submissionId: string;
};

const initialInput: TripPlannerInput = {
  fromCity: "",
  travelDate: "",
  returnDate: "",
  travellersCount: 2,
  hasSeniorCitizens: false,
  travelMode: "not_sure",
  stayCityPreference: "not_sure",
  budget: "standard",
  needsDarshanHelp: false,
  needsLocalTransport: false,
};

export function PlanAndBook({ affiliateConfig }: { affiliateConfig: AffiliateLinkConfig }) {
  const [input, setInput] = useState(initialInput);
  const [result, setResult] = useState<ResultState | null>(null);
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackOption[]>([]);
  const [otherFeedback, setOtherFeedback] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [formError, setFormError] = useState("");
  const resultRef = useRef<HTMLDivElement>(null);
  const minimumDate = useMemo(() => new Date().toISOString().slice(0, 10), []);

  function update<K extends keyof TripPlannerInput>(key: K, value: TripPlannerInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
  }

  function submitTrip(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (input.returnDate < input.travelDate) {
      setFormError("Return date must be on or after the travel date.");
      return;
    }
    setFormError("");
    const recommendation = generateTripRecommendation(input);
    const links = generateAffiliateLinks(input, recommendation, affiliateConfig);
    const submission = saveTripSubmission(input, recommendation);
    setResult({ input, recommendation, links, submissionId: submission.id });
    setSelectedFeedback([]);
    setOtherFeedback("");
    setFeedbackSent(false);
    trackPlannerEvent("trip_form_submitted", {
      travel_mode: input.travelMode,
      stay_preference: input.stayCityPreference,
      recommended_stay_city: recommendation.stayCity,
      travellers_count: input.travellersCount,
      has_senior_citizens: input.hasSeniorCitizens,
    });
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }

  function toggleFeedback(option: FeedbackOption) {
    setSelectedFeedback((current) => current.includes(option) ? current.filter((item) => item !== option) : [...current, option]);
  }

  function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!result || selectedFeedback.length === 0) return;
    saveTripFeedback({
      submissionId: result.submissionId,
      useful: true,
      options: selectedFeedback,
      otherText: selectedFeedback.includes("Other") ? otherFeedback.trim() : undefined,
    });
    trackPlannerEvent("feedback_submitted", { options: selectedFeedback, recommended_stay_city: result.recommendation.stayCity });
    setFeedbackSent(true);
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(340px,.95fr)] lg:items-start">
      <form onSubmit={submitTrip} className="overflow-hidden rounded-[2rem] border border-gold/35 bg-white shadow-soft">
        <div className="brand-gradient pattern-jaali p-6 text-white sm:p-8">
          <p className="text-xs font-black uppercase tracking-[.2em] text-gold">Free Phase-1 planner</p>
          <h2 className="mt-3 font-serif text-3xl text-white sm:text-4xl">Tell us what your family needs</h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-orange-50/80">No account required. We create a practical starting plan; partner sites handle availability, prices and booking.</p>
        </div>

        <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-8">
          <Field label="Starting city" className="sm:col-span-2">
            <input required value={input.fromCity} onChange={(event) => update("fromCity", event.target.value)} className="form-control" placeholder="e.g. Delhi, Mumbai, Ahmedabad" autoComplete="address-level2" />
          </Field>
          <Field label="Travel date">
            <input required type="date" min={minimumDate} value={input.travelDate} onChange={(event) => update("travelDate", event.target.value)} className="form-control" />
          </Field>
          <Field label="Return date">
            <input required type="date" min={input.travelDate || minimumDate} value={input.returnDate} onChange={(event) => update("returnDate", event.target.value)} className="form-control" />
          </Field>
          <Field label="Number of travellers">
            <input required type="number" min="1" max="30" value={input.travellersCount} onChange={(event) => update("travellersCount", Number(event.target.value))} className="form-control" />
          </Field>
          <Field label="Travel mode">
            <select value={input.travelMode} onChange={(event) => update("travelMode", event.target.value as TripPlannerInput["travelMode"])} className="form-control">
              {travelModes.map((mode) => <option key={mode} value={mode}>{formatLabel(mode)}</option>)}
            </select>
          </Field>
          <Field label="Preferred stay city">
            <select value={input.stayCityPreference} onChange={(event) => update("stayCityPreference", event.target.value as TripPlannerInput["stayCityPreference"])} className="form-control">
              {stayCities.map((city) => <option key={city} value={city}>{formatLabel(city)}</option>)}
            </select>
          </Field>
          <Field label="Budget">
            <select value={input.budget} onChange={(event) => update("budget", event.target.value as TripPlannerInput["budget"])} className="form-control">
              {budgetLevels.map((budget) => <option key={budget} value={budget}>{formatLabel(budget)}</option>)}
            </select>
          </Field>

          <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
            <CheckOption checked={input.hasSeniorCitizens} onChange={(value) => update("hasSeniorCitizens", value)} label="Senior citizens travelling" icon={HeartHandshake} />
            <CheckOption checked={input.needsDarshanHelp} onChange={(value) => update("needsDarshanHelp", value)} label="Need darshan guidance" icon={Landmark} />
            <CheckOption checked={input.needsLocalTransport} onChange={(value) => update("needsLocalTransport", value)} label="Need local transport" icon={BusFront} />
          </div>

          <Button type="submit" size="lg" className="mt-2 w-full sm:col-span-2">
            Build My Plan & Booking Options <ArrowRight className="h-4 w-4" />
          </Button>
          {formError && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-center text-sm font-semibold text-red-800 sm:col-span-2">{formError}</p>}
          <p className="text-center text-xs leading-5 text-stone-500 sm:col-span-2">Your anonymous plan is stored only in this browser for this MVP. No booking or payment details are collected.</p>
        </div>
      </form>

      <div ref={resultRef} className="scroll-mt-32">
        {result ? <RecommendationResult result={result} /> : <EmptyResult />}
      </div>

      {result && (
        <div className="lg:col-span-2">
          <FeedbackForm
            selected={selectedFeedback}
            otherFeedback={otherFeedback}
            sent={feedbackSent}
            onToggle={toggleFeedback}
            onOtherChange={setOtherFeedback}
            onSubmit={submitFeedback}
          />
        </div>
      )}
    </div>
  );
}

function RecommendationResult({ result }: { result: ResultState }) {
  const { input, recommendation, links } = result;
  return (
    <Card className="overflow-hidden border-gold/40 bg-[#fffdf8]">
      <div className="bg-maroon p-6 text-white sm:p-8">
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="text-xs font-black uppercase tracking-[.2em] text-gold">Your practical starting plan</p>
            <h2 className="mt-3 font-serif text-3xl text-white">Stay in {recommendation.stayCity}</h2>
          </div>
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-gold"><Hotel className="h-6 w-6" /></span>
        </div>
        <p className="mt-4 text-sm leading-7 text-orange-50/85">{recommendation.stayReason}</p>
      </div>
      <CardContent className="space-y-5 p-5 sm:p-7">
        <ResultBlock icon={Route} title="Suggested travel route" text={recommendation.routeSuggestion} />
        <ResultBlock icon={Users} title="Kumbh crowd planning" text={recommendation.crowdPlanningNote} tone="warning" />
        <div className="rounded-2xl border border-stone-200 bg-white p-5">
          <h3 className="flex items-center gap-2 font-bold text-ink"><Sparkles className="h-4 w-4 text-gold-dark" />Before you book</h3>
          <ul className="mt-4 space-y-3">
            {recommendation.practicalActions.map((action) => <li key={action} className="flex gap-2 text-sm leading-6 text-stone-600"><Check className="mt-1 h-4 w-4 shrink-0 text-[#168f4d]" />{action}</li>)}
          </ul>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <a
            href={links.travelUrl}
            target="_blank"
            rel="sponsored noreferrer"
            onClick={() => trackPlannerEvent("travel_cta_clicked", { travel_mode: input.travelMode, destination_city: recommendation.destinationCity })}
            className="flex min-h-14 items-center justify-center gap-2 rounded-full bg-saffron px-5 text-center text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-[#d95b22]"
          >
            <TicketCheck className="h-5 w-5" />Check Travel Options<ExternalLink className="h-4 w-4" />
          </a>
          <a
            href={links.hotelUrl}
            target="_blank"
            rel="sponsored noreferrer"
            onClick={() => trackPlannerEvent("hotel_cta_clicked", { recommended_stay_city: recommendation.stayCity, budget: input.budget })}
            className="flex min-h-14 items-center justify-center gap-2 rounded-full bg-maroon px-5 text-center text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-[#4f171d]"
          >
            <BedDouble className="h-5 w-5" />Check Hotel Options<ExternalLink className="h-4 w-4" />
          </a>
        </div>
        {(!links.travelPartnerConfigured || !links.hotelPartnerConfigured) && (
          <p className="rounded-xl bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">Affiliate partner URLs are not configured yet, so these buttons currently open public partner search pages with your trip details where supported.</p>
        )}
        <div className="flex gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-950">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
          <p><strong>Booking trust note:</strong> Booking is completed on partner websites. indiankumbh.com helps you plan and compare.</p>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyResult() {
  return (
    <Card className="border-dashed border-gold/50 bg-sand">
      <CardContent className="p-7 sm:p-9">
        <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white text-maroon shadow-sm"><MapPin className="h-7 w-7" /></span>
        <h2 className="mt-6 font-serif text-3xl">Your recommendation will appear here</h2>
        <p className="mt-3 text-sm leading-7 text-stone-600">We will recommend Ujjain, Indore or Bhopal, suggest a sensible route and create travel and hotel search links—without calling a paid API.</p>
        <div className="mt-6 grid gap-3 text-sm font-semibold text-stone-700">
          {["No account needed", "No payment details collected", "Official arrangements must still be verified"].map((item) => <p key={item} className="flex items-center gap-2"><Check className="h-4 w-4 text-[#168f4d]" />{item}</p>)}
        </div>
      </CardContent>
    </Card>
  );
}

function FeedbackForm({
  selected,
  otherFeedback,
  sent,
  onToggle,
  onOtherChange,
  onSubmit,
}: {
  selected: FeedbackOption[];
  otherFeedback: string;
  sent: boolean;
  onToggle: (option: FeedbackOption) => void;
  onOtherChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="rounded-[2rem] border border-gold/35 bg-white p-6 shadow-soft sm:p-9">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Help shape the MVP</p><h2 className="mt-2 font-serif text-3xl">Was this useful?</h2><p className="mt-2 text-sm text-stone-600">What should we improve before your family would rely on this planner?</p></div>
        {sent && <p className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-800"><Check className="h-4 w-4" />Feedback saved</p>}
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        {feedbackOptions.map((option) => {
          const active = selected.includes(option);
          return <button key={option} type="button" aria-pressed={active} onClick={() => onToggle(option)} className={`rounded-full border px-4 py-2.5 text-sm font-semibold transition ${active ? "border-saffron bg-orange-50 text-maroon ring-2 ring-orange-100" : "border-stone-200 bg-white text-stone-600 hover:border-gold"}`}>{option}</button>;
        })}
      </div>
      {selected.includes("Other") && <textarea value={otherFeedback} onChange={(event) => onOtherChange(event.target.value)} rows={3} maxLength={500} placeholder="Tell us what is missing…" className="mt-5 w-full rounded-2xl border border-stone-300 bg-white p-4 text-sm outline-none focus:border-saffron focus:ring-4 focus:ring-orange-100" />}
      <Button type="submit" variant="maroon" className="mt-6" disabled={selected.length === 0 || sent}>Submit Feedback</Button>
    </form>
  );
}

function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return <label className={`text-sm font-bold text-ink ${className}`}>{label}{children}</label>;
}

function CheckOption({ checked, onChange, label, icon: Icon }: { checked: boolean; onChange: (value: boolean) => void; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <label className={`flex min-h-20 cursor-pointer items-center gap-3 rounded-2xl border p-4 transition ${checked ? "border-saffron bg-orange-50 ring-2 ring-orange-100" : "border-stone-200 hover:border-gold"}`}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="sr-only" />
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${checked ? "bg-saffron text-white" : "bg-sand text-maroon"}`}><Icon className="h-5 w-5" /></span>
      <span className="flex-1 text-sm font-bold leading-5">{label}</span>
      <span className={`grid h-5 w-5 place-items-center rounded-full border ${checked ? "border-saffron bg-saffron text-white" : "border-stone-300"}`}>{checked && <Check className="h-3 w-3" />}</span>
    </label>
  );
}

function ResultBlock({ icon: Icon, title, text, tone = "default" }: { icon: React.ComponentType<{ className?: string }>; title: string; text: string; tone?: "default" | "warning" }) {
  return (
    <div className={`rounded-2xl border p-5 ${tone === "warning" ? "border-amber-200 bg-amber-50" : "border-stone-200 bg-white"}`}>
      <h3 className="flex items-center gap-2 font-bold text-ink"><Icon className={`h-5 w-5 ${tone === "warning" ? "text-amber-700" : "text-saffron"}`} />{title}</h3>
      <p className="mt-3 text-sm leading-7 text-stone-600">{text}</p>
    </div>
  );
}

function formatLabel(value: string) {
  if (value === "not_sure") return "Not sure — recommend for me";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
