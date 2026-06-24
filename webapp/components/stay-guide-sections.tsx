"use client";

import { useMemo, useState } from "react";
import {
  ArrowRight,
  BedDouble,
  Building2,
  Check,
  CircleDollarSign,
  Landmark,
  MapPin,
  MessageCircle,
  Plane,
  Send,
  ShoppingBag,
  Trees,
  Users,
} from "lucide-react";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";

const recommendationIcons = { temple: Landmark, plane: Plane, heritage: Building2 };

export function StayRecommendationCard({ item, featured = false }: { item: { city: string; headline: string; description: string; icon: string }; featured?: boolean }) {
  const Icon = recommendationIcons[item.icon as keyof typeof recommendationIcons] ?? BedDouble;
  return (
    <Card className={`h-full overflow-hidden ${featured ? "border-maroon ring-2 ring-maroon/10" : "border-gold/35"}`}>
      <div className={`${featured ? "brand-gradient" : "bg-sand"} temple-silhouette p-6 ${featured ? "text-white" : "text-ink"}`}>
        <Icon className={`h-7 w-7 ${featured ? "text-gold" : "text-saffron"}`} />
        <p className={`mt-5 text-xs font-extrabold uppercase tracking-[.18em] ${featured ? "text-gold" : "text-saffron"}`}>{item.city}</p>
        <h3 className={`mt-2 font-serif text-2xl ${featured ? "text-white" : "text-ink"}`}>{item.headline}</h3>
      </div>
      <CardContent><p className="text-sm leading-7 text-stone-600">{item.description}</p></CardContent>
    </Card>
  );
}

type Comparison = { city: string; bestFor: string; pros: string[]; cons: string[]; idealVisitor: string; duration: string };
export function DetailedStayComparison({ items }: { items: Comparison[] }) {
  return (
    <div className="overflow-x-auto rounded-3xl border border-gold/40 bg-white shadow-soft">
      <table className="min-w-[1050px] w-full text-left">
        <thead className="bg-maroon text-xs uppercase tracking-wider text-white"><tr>{["Base City", "Best For", "Pros", "Cons", "Ideal Visitor", "Suggested Stay"].map((label) => <th key={label} className="px-5 py-4 font-bold">{label}</th>)}</tr></thead>
        <tbody className="divide-y divide-stone-200">
          {items.map((item, index) => <tr key={item.city} className={index === 0 ? "bg-orange-50/35" : "bg-white"}>
            <td className="px-5 py-5 align-top"><strong className="font-serif text-xl">{item.city}</strong></td>
            <td className="max-w-44 px-5 py-5 align-top text-sm leading-6 text-stone-600">{item.bestFor}</td>
            <td className="px-5 py-5 align-top"><List items={item.pros} positive /></td>
            <td className="px-5 py-5 align-top"><List items={item.cons} /></td>
            <td className="max-w-56 px-5 py-5 align-top text-sm leading-6 text-stone-600">{item.idealVisitor}</td>
            <td className="px-5 py-5 align-top text-sm font-bold text-maroon">{item.duration}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  );
}

function List({ items, positive = false }: { items: string[]; positive?: boolean }) {
  return <ul className="min-w-44 space-y-2">{items.map((item) => <li key={item} className="flex gap-2 text-xs leading-5 text-stone-600"><Check className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${positive ? "text-[#168f4d]" : "text-stone-400"}`} />{item}</li>)}</ul>;
}

export function AreaGuideCard({ city, areas }: { city: string; areas: { name: string; bestFor: string; note: string }[] }) {
  return (
    <Card className="h-full overflow-hidden">
      <div className="brand-gradient temple-silhouette p-6 text-white"><MapPin className="h-6 w-6 text-gold" /><h3 className="mt-4 font-serif text-3xl text-white">{city} area guide</h3></div>
      <CardContent className="space-y-5">{areas.map((area) => <div key={area.name} className="border-b border-stone-200 pb-5 last:border-0 last:pb-0"><div className="flex flex-wrap items-baseline justify-between gap-2"><h4 className="font-bold">{area.name}</h4><span className="text-xs font-bold text-saffron">{area.bestFor}</span></div><p className="mt-2 text-sm leading-6 text-stone-600">{area.note}</p></div>)}</CardContent>
    </Card>
  );
}

const quizIcons = [Users, Plane, ShoppingBag, Trees, Landmark];
export function FamilyStayQuiz({ items }: { items: { question: string; recommendation: string; reason: string }[] }) {
  const [answers, setAnswers] = useState<boolean[]>(items.map(() => false));
  const result = useMemo(() => {
    const scores = { Ujjain: 0, Indore: 0, Bhopal: 0 };
    answers.forEach((answer, index) => { if (answer) scores[items[index].recommendation as keyof typeof scores] += 1; });
    const selected = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
    return selected[1] > 0 ? selected[0] : null;
  }, [answers, items]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1.25fr_.75fr]">
      <div className="grid gap-4 sm:grid-cols-2">
        {items.map((item, index) => {
          const Icon = quizIcons[index] || BedDouble;
          const active = answers[index];
          return <button key={item.question} onClick={() => setAnswers((current) => current.map((value, i) => i === index ? !value : value))} className={`rounded-2xl border p-5 text-left transition ${active ? "border-saffron bg-orange-50 ring-2 ring-orange-100" : "border-stone-200 bg-white hover:border-gold"}`}><div className="flex items-start justify-between"><Icon className="h-6 w-6 text-saffron" /><span className={`grid h-6 w-6 place-items-center rounded-full border ${active ? "border-saffron bg-saffron text-white" : "border-stone-300"}`}>{active && <Check className="h-4 w-4" />}</span></div><p className="mt-4 font-bold">{item.question}</p><p className="mt-2 text-xs leading-5 text-stone-500">{item.reason}</p></button>;
        })}
      </div>
      <Card className="brand-gradient temple-silhouette h-fit border-gold/50 text-white">
        <CardContent>
          <p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Current recommendation</p>
          <h3 className="mt-4 font-serif text-4xl text-white">{result || "Select what matters"}</h3>
          <p className="mt-4 text-sm leading-7 text-orange-50/75">{result ? `Based on your selected priorities, ${result} is the strongest starting base. Review the comparison table before booking.` : "Tap one or more questions to get a simple city recommendation."}</p>
        </CardContent>
      </Card>
    </div>
  );
}

const budgetIcons = [Landmark, CircleDollarSign, BedDouble, Building2, Users];
export function StayBudgetCards({ items }: { items: { category: string; positioning: string; bestFor: string; notes: string }[] }) {
  return <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">{items.map((item, index) => { const Icon = budgetIcons[index] || BedDouble; return <Card key={item.category} className="h-full border-t-4 border-t-gold"><CardContent><Icon className="h-6 w-6 text-saffron" /><p className="mt-5 text-xs font-bold uppercase tracking-widest text-saffron">{item.positioning}</p><h3 className="mt-2 font-serif text-xl">{item.category}</h3><p className="mt-4 text-sm font-bold text-maroon">{item.bestFor}</p><p className="mt-3 text-xs leading-5 text-stone-600">{item.notes}</p></CardContent></Card>; })}</div>;
}

export function StayHelpForm() {
  const [submitted, setSubmitted] = useState(false);
  return (
    <div className="brand-gradient temple-silhouette overflow-hidden rounded-[2rem] border border-gold/40 p-6 text-white shadow-soft sm:p-10">
      <div className="grid gap-8 lg:grid-cols-[.75fr_1.25fr]">
        <div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Mock stay enquiry</p><h2 className="mt-3 font-serif text-4xl text-white">Need help choosing stay base?</h2><p className="mt-4 leading-7 text-orange-50/75">Share the basics and we’ll show a demo confirmation. No message is sent yet.</p></div>
        {submitted ? <div className="grid min-h-72 place-items-center rounded-2xl border border-white/15 bg-white/10 p-8 text-center"><div><Check className="mx-auto h-10 w-10 text-gold" /><h3 className="mt-4 font-serif text-2xl text-white">Enquiry captured for preview</h3><p className="mt-3 text-sm text-orange-50/70">This is a mock submission. Connect a backend or WhatsApp workflow before launch.</p><Button onClick={() => setSubmitted(false)} variant="outline" className="mt-6">Submit another</Button></div></div> :
        <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }} className="grid gap-4 rounded-2xl bg-white p-5 text-ink sm:grid-cols-2 sm:p-7">
          <FormField label="Preferred city"><select required className="form-control"><option value="">Select city</option><option>Ujjain</option><option>Indore</option><option>Bhopal</option><option>Not sure</option></select></FormField>
          <FormField label="Family size"><input required min="1" type="number" className="form-control" placeholder="4" /></FormField>
          <FormField label="Travel dates"><input required type="text" className="form-control" placeholder="Approximate dates" /></FormField>
          <FormField label="Stay preference"><select required className="form-control"><option value="">Select preference</option><option>Dharamshala / Ashram</option><option>Budget hotel</option><option>Mid-range hotel</option><option>Premium hotel</option><option>Apartment / homestay</option></select></FormField>
          <FormField label="WhatsApp number"><input required type="tel" className="form-control" placeholder="+91 98XXXXXX00" /></FormField>
          <div className="flex items-end"><Button type="submit" className="h-12 w-full"><Send className="h-4 w-4" />Preview enquiry</Button></div>
          <p className="text-xs leading-5 text-stone-500 sm:col-span-2"><MessageCircle className="mr-1 inline h-3.5 w-3.5" />Mock only: details remain in the browser and are not transmitted.</p>
        </form>}
      </div>
    </div>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="text-sm font-bold text-stone-700">{label}{children}</label>;
}
