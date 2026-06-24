"use client";

import { FormEvent, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Check, HeartHandshake, Landmark, Loader2, ShieldCheck, Users } from "lucide-react";
import type { PackageCategory } from "@/src/data/packageCategories";
import { Button } from "@/components/ui/button";

type FormState = {
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
};

const initialState: FormState = {
  fullName: "",
  mobile: "",
  whatsappNumber: "",
  email: "",
  sourceCity: "",
  travelMonth: "",
  numberOfAdults: 2,
  numberOfChildren: 0,
  hasSeniorCitizens: false,
  budgetPerPerson: "",
  stayPreference: "Not Sure",
  packageType: "",
  needMahakalDarshanSupport: false,
  needTransport: false,
  message: "",
  consentAccepted: false,
  honeypot: "",
};

export function PackageLeadForm({
  packageCategories,
  destination = "Ujjain Kumbh 2028",
}: {
  packageCategories: Pick<PackageCategory, "slug" | "title">[];
  destination?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [form, setForm] = useState<FormState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const queryPackage = new URLSearchParams(window.location.search).get("packageType") || "";
    if (packageCategories.some((item) => item.slug === queryPackage)) {
      setForm((current) => ({ ...current, packageType: queryPackage }));
    }
  }, [packageCategories]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const normalizedMobile = form.mobile.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "").replace(/^0(?=\d{10}$)/, "");
    if (!/^[6-9]\d{9}$/.test(normalizedMobile)) {
      setError("Please enter a valid 10-digit Indian mobile number.");
      return;
    }
    if (!form.consentAccepted) {
      setError("Please accept the consent statement before submitting.");
      return;
    }

    setSubmitting(true);
    try {
      const query = new URLSearchParams(window.location.search);
      const response = await fetch("/api/package-enquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          sourcePage: pathname,
          utmSource: query.get("utm_source") || "",
          utmMedium: query.get("utm_medium") || "",
          utmCampaign: query.get("utm_campaign") || "",
        }),
      });
      const result = await response.json() as { success?: boolean; enquiryId?: string; error?: string };
      if (!response.ok || !result.success) throw new Error(result.error || "We could not submit your enquiry.");
      router.push(`/thank-you/package-enquiry?id=${encodeURIComponent(result.enquiryId || "")}`);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "We could not submit your enquiry. Please try again or email support@indiankumbh.com.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="overflow-hidden rounded-[2rem] border border-gold/35 bg-white shadow-soft">
      <div className="brand-gradient pattern-jaali p-6 text-white sm:p-8">
        <p className="text-xs font-black uppercase tracking-[.2em] text-gold">Package enquiry · {destination}</p>
        <h2 className="mt-3 font-serif text-3xl text-white sm:text-4xl">Tell us what your family needs</h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-orange-50/80">Your enquiry will be shared only with verified travel partners relevant to your trip.</p>
      </div>

      <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-8">
        <Field label="Full name"><input required autoComplete="name" value={form.fullName} onChange={(event) => update("fullName", event.target.value)} className="form-control" /></Field>
        <Field label="Mobile number"><input required inputMode="tel" autoComplete="tel" placeholder="10-digit Indian mobile" value={form.mobile} onChange={(event) => update("mobile", event.target.value)} className="form-control" /></Field>
        <Field label="WhatsApp number"><input inputMode="tel" placeholder="Leave blank if same as mobile" value={form.whatsappNumber} onChange={(event) => update("whatsappNumber", event.target.value)} className="form-control" /></Field>
        <Field label="Email"><input type="email" autoComplete="email" value={form.email} onChange={(event) => update("email", event.target.value)} className="form-control" /></Field>
        <Field label="Starting city"><input required autoComplete="address-level2" value={form.sourceCity} onChange={(event) => update("sourceCity", event.target.value)} className="form-control" /></Field>
        <Field label="Travel month"><input type="month" value={form.travelMonth} onChange={(event) => update("travelMonth", event.target.value)} className="form-control" /></Field>
        <Field label="Number of adults"><input type="number" min="1" max="100" value={form.numberOfAdults} onChange={(event) => update("numberOfAdults", Number(event.target.value))} className="form-control" /></Field>
        <Field label="Number of children"><input type="number" min="0" max="100" value={form.numberOfChildren} onChange={(event) => update("numberOfChildren", Number(event.target.value))} className="form-control" /></Field>
        <Field label="Budget per person">
          <select value={form.budgetPerPerson} onChange={(event) => update("budgetPerPerson", event.target.value)} className="form-control">
            <option value="">Select approximate budget</option>
            <option value="Below ₹5,000">Below ₹5,000</option><option value="₹5,000–₹10,000">₹5,000–₹10,000</option><option value="₹10,000–₹20,000">₹10,000–₹20,000</option><option value="Above ₹20,000">Above ₹20,000</option><option value="Not sure">Not sure</option>
          </select>
        </Field>
        <Field label="Stay preference">
          <select value={form.stayPreference} onChange={(event) => update("stayPreference", event.target.value as FormState["stayPreference"])} className="form-control">
            {["Ujjain", "Indore", "Bhopal", "Not Sure"].map((city) => <option key={city}>{city}</option>)}
          </select>
        </Field>
        <Field label="Package type" className="sm:col-span-2">
          <select required value={form.packageType} onChange={(event) => update("packageType", event.target.value)} className="form-control">
            <option value="">Select package type</option>
            {packageCategories.map((category) => <option key={category.slug} value={category.slug}>{category.title}</option>)}
          </select>
        </Field>

        <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
          <Toggle checked={form.hasSeniorCitizens} onChange={(value) => update("hasSeniorCitizens", value)} label="Senior citizens travelling" icon={HeartHandshake} />
          <Toggle checked={form.needMahakalDarshanSupport} onChange={(value) => update("needMahakalDarshanSupport", value)} label="Need Mahakal darshan support" icon={Landmark} />
          <Toggle checked={form.needTransport} onChange={(value) => update("needTransport", value)} label="Need local transport" icon={Users} />
        </div>

        <Field label="Anything else we should know?" className="sm:col-span-2">
          <textarea rows={4} maxLength={1000} value={form.message} onChange={(event) => update("message", event.target.value)} className="mt-2 w-full rounded-2xl border border-stone-300 bg-white p-4 font-normal outline-none focus:border-saffron focus:ring-4 focus:ring-orange-100" />
        </Field>

        <div className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
          <label>Leave this field empty<input tabIndex={-1} autoComplete="off" value={form.honeypot} onChange={(event) => update("honeypot", event.target.value)} /></label>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-stone-200 bg-cream p-4 text-sm leading-6 text-stone-700 sm:col-span-2">
          <input required type="checkbox" checked={form.consentAccepted} onChange={(event) => update("consentAccepted", event.target.checked)} className="mt-1 h-5 w-5 accent-[#e8672a]" />
          <span><strong>Consent:</strong> I agree that IndianKumbh.com may use these details to respond to my enquiry and share them with relevant verified travel partners. I understand that partners confirm final prices, availability and booking terms.</span>
        </label>

        {error && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 sm:col-span-2">{error}</p>}
        <Button type="submit" size="lg" disabled={submitting} className="w-full sm:col-span-2">
          {submitting ? <><Loader2 className="h-4 w-4 animate-spin" />Submitting enquiry…</> : <>Request Package Quote<Check className="h-4 w-4" /></>}
        </Button>
        <p className="flex items-start justify-center gap-2 text-center text-xs leading-5 text-stone-500 sm:col-span-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#168f4d]" />No payment is collected. For help, contact support@indiankumbh.com.</p>
      </div>
    </form>
  );
}

function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return <label className={`text-sm font-bold text-ink ${className}`}>{label}{children}</label>;
}

function Toggle({ checked, onChange, label, icon: Icon }: { checked: boolean; onChange: (value: boolean) => void; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return <label className={`flex min-h-20 cursor-pointer items-center gap-3 rounded-2xl border p-4 ${checked ? "border-saffron bg-orange-50 ring-2 ring-orange-100" : "border-stone-200"}`}><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="sr-only" /><Icon className={`h-5 w-5 shrink-0 ${checked ? "text-saffron" : "text-maroon"}`} /><span className="flex-1 text-sm font-bold leading-5">{label}</span><span className={`grid h-5 w-5 place-items-center rounded-full border ${checked ? "border-saffron bg-saffron text-white" : "border-stone-300"}`}>{checked && <Check className="h-3 w-3" />}</span></label>;
}
