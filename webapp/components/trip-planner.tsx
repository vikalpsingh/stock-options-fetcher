"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  BedDouble,
  Check,
  Clock3,
  Compass,
  HeartHandshake,
  Landmark,
  MapPin,
  MessageCircle,
  Navigation,
  Route,
  Sparkles,
  Soup,
  Users,
} from "lucide-react";
import planner from "@/data/trip-planner.json";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { WorkingPrintButton } from "./print-button";

type Answers = {
  startingCity: string;
  days: number | null;
  visitorType: string;
  stayPreference: string;
  interests: string[];
};

const initialAnswers: Answers = { startingCity: "", days: null, visitorType: "", stayPreference: "", interests: [] };
const stepLabels = ["Start", "Duration", "Visitors", "Stay", "Interests"];

export function TripPlanner() {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Answers>(initialAnswers);
  const [showResult, setShowResult] = useState(false);

  const canContinue = [
    Boolean(answers.startingCity),
    Boolean(answers.days),
    Boolean(answers.visitorType),
    Boolean(answers.stayPreference),
    answers.interests.length > 0,
  ][step];

  const result = useMemo(() => buildResult(answers), [answers]);

  const chooseSingle = (key: keyof Omit<Answers, "interests">, value: string | number) => {
    setAnswers((current) => ({ ...current, [key]: value }));
  };
  const toggleInterest = (interest: string) => {
    setAnswers((current) => ({ ...current, interests: current.interests.includes(interest) ? current.interests.filter((item) => item !== interest) : [...current.interests, interest] }));
  };
  const next = () => {
    if (!canContinue) return;
    if (step === stepLabels.length - 1) setShowResult(true);
    else setStep((current) => current + 1);
  };
  const reset = () => { setAnswers(initialAnswers); setStep(0); setShowResult(false); };

  return (
    <div>
      <WizardProgress step={showResult ? 5 : step} />
      <AnimatePresence mode="wait">
        {!showResult ? (
          <motion.div key={`step-${step}`} initial={{ opacity: 0, x: 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -28 }} transition={{ duration: 0.28 }}>
            <Card className="mx-auto mt-8 max-w-4xl overflow-hidden border-gold/40">
              <div className="brand-gradient temple-silhouette p-6 text-white sm:p-8">
                <p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Step {step + 1} of 5</p>
                <h2 className="mt-3 font-serif text-3xl text-white sm:text-4xl">{questionForStep(step)}</h2>
                <p className="mt-3 text-sm text-orange-50/70">{helperForStep(step)}</p>
              </div>
              <CardContent className="p-5 sm:p-8">
                {step === 0 && <OptionGrid options={planner.startingCities} selected={answers.startingCity ? [answers.startingCity] : []} onSelect={(value) => chooseSingle("startingCity", value)} icon={MapPin} />}
                {step === 1 && <OptionGrid options={planner.days.map((day) => `${day} ${day === 1 ? "day" : "days"}`)} selected={answers.days ? [`${answers.days} ${answers.days === 1 ? "day" : "days"}`] : []} onSelect={(value) => chooseSingle("days", Number(value.split(" ")[0]))} icon={Clock3} />}
                {step === 2 && <OptionGrid options={planner.visitorTypes} selected={answers.visitorType ? [answers.visitorType] : []} onSelect={(value) => chooseSingle("visitorType", value)} icon={Users} />}
                {step === 3 && <OptionGrid options={planner.stayPreferences} selected={answers.stayPreference ? [answers.stayPreference] : []} onSelect={(value) => chooseSingle("stayPreference", value)} icon={BedDouble} />}
                {step === 4 && <OptionGrid options={planner.interests} selected={answers.interests} onSelect={toggleInterest} icon={Compass} multiple />}
                <div className="mt-8 flex items-center justify-between gap-3">
                  <Button variant="ghost" disabled={step === 0} onClick={() => setStep((current) => Math.max(0, current - 1))}><ArrowLeft className="h-4 w-4" />Back</Button>
                  <Button size="lg" disabled={!canContinue} onClick={next}>{step === 4 ? "Generate My Trip" : "Continue"}<ArrowRight className="h-4 w-4" /></Button>
                </div>
                <p className="mt-5 text-center text-xs text-stone-400">Your choices stay only in this page and are not stored or submitted.</p>
              </CardContent>
            </Card>
          </motion.div>
        ) : (
          <motion.div key="result" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.42 }}>
            <TripResult answers={answers} result={result} onReset={reset} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function WizardProgress({ step }: { step: number }) {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between gap-1">
        {stepLabels.map((label, index) => <div key={label} className="flex flex-1 items-center last:flex-none"><div className="flex flex-col items-center gap-2"><span className={`grid h-9 w-9 place-items-center rounded-full text-xs font-bold transition ${index < step ? "bg-[#168f4d] text-white" : index === step ? "bg-saffron text-white ring-4 ring-orange-100" : "bg-white text-stone-400 ring-1 ring-stone-200"}`}>{index < step ? <Check className="h-4 w-4" /> : index + 1}</span><span className="hidden text-[10px] font-bold uppercase tracking-wider text-stone-500 sm:block">{label}</span></div>{index < stepLabels.length - 1 && <span className={`mx-2 h-0.5 flex-1 ${index < step ? "bg-[#168f4d]" : "bg-stone-200"}`} />}</div>)}
      </div>
    </div>
  );
}

function OptionGrid({ options, selected, onSelect, icon: Icon, multiple = false }: { options: readonly string[]; selected: string[]; onSelect: (value: string) => void; icon: React.ComponentType<{ className?: string }>; multiple?: boolean }) {
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{options.map((option) => { const active = selected.includes(option); return <button key={option} onClick={() => onSelect(option)} className={`group flex min-h-20 items-center gap-4 rounded-2xl border p-4 text-left transition ${active ? "border-saffron bg-orange-50 ring-2 ring-orange-100" : "border-stone-200 bg-white hover:border-gold hover:shadow-sm"}`}><span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${active ? "bg-saffron text-white" : "bg-sand text-maroon"}`}><Icon className="h-5 w-5" /></span><span className="flex-1 font-bold text-ink">{option}</span><span className={`grid h-5 w-5 place-items-center rounded-full border ${active ? "border-saffron bg-saffron text-white" : "border-stone-300"}`}>{active && <Check className="h-3 w-3" />}</span>{multiple && <span className="sr-only">Toggle</span>}</button>; })}</div>;
}

function TripResult({ answers, result, onReset }: { answers: Answers; result: ReturnType<typeof buildResult>; onReset: () => void }) {
  const shareText = `My ${answers.days}-day Ujjain plan from ${answers.startingCity}. Best base: ${result.base}. ${result.itinerary.join(" ")}`;
  return (
    <div id="print-itinerary" className="mt-8 overflow-hidden rounded-[2rem] border border-gold/40 bg-white shadow-soft">
      <div className="brand-gradient temple-silhouette p-6 text-white sm:p-10">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Your rule-based trip plan</p><h2 className="mt-3 font-serif text-4xl text-white sm:text-5xl">{answers.days}-day Ujjain journey</h2><p className="mt-3 text-orange-50/75">From {answers.startingCity} · {answers.visitorType} · {answers.interests.join(", ")}</p></div>
          <div className="rounded-2xl border border-white/15 bg-black/15 p-5"><p className="text-xs uppercase tracking-wider text-gold">Best base city</p><p className="mt-1 font-serif text-3xl text-white">{result.base}</p></div>
        </div>
      </div>
      <div className="p-5 sm:p-8">
        <div className="grid gap-6 lg:grid-cols-[1.35fr_.65fr]">
          <div>
            <h3 className="font-serif text-2xl">Suggested itinerary</h3>
            <ol className="relative mt-6 ml-4 border-l border-gold/50 pl-8">{result.itinerary.map((item, index) => <li key={item} className="relative pb-7 last:pb-0"><span className="absolute -left-[42px] grid h-7 w-7 place-items-center rounded-full bg-saffron text-xs font-bold text-white ring-4 ring-orange-50">{index + 1}</span><p className="text-sm leading-7 text-stone-700">{item}</p></li>)}</ol>
          </div>
          <div className="space-y-4">
            <ResultBlock icon={Route} title="Travel placeholder" items={[result.travelTime]} />
            <ResultBlock icon={Landmark} title="Must-visit temples" items={result.temples} />
            <ResultBlock icon={MapPin} title="Nearby places" items={result.nearby.length ? result.nearby : ["Keep this trip focused within Ujjain"]} />
          </div>
        </div>
        <div className="mt-7 grid gap-5 md:grid-cols-2">
          <ResultBlock icon={Soup} title="Food suggestions" items={result.food} />
          <ResultBlock icon={HeartHandshake} title="Elderly-friendly tips" items={result.elderlyTips} />
        </div>
        <div className="print-hidden mt-8 flex flex-wrap gap-3 border-t border-stone-200 pt-7">
          <Button asChild variant="outline"><a href={`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(answers.startingCity)}&destination=Ujjain`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" />Route to Ujjain</a></Button>
          {result.nearby.slice(0, 2).map((place) => <Button key={place} asChild variant="outline"><a href={`https://www.google.com/maps/dir/?api=1&origin=Ujjain&destination=${encodeURIComponent(place)}`} target="_blank" rel="noreferrer"><MapPin className="h-4 w-4" />Map {place}</a></Button>)}
          <Button asChild variant="whatsapp"><a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4" />WhatsApp plan</a></Button>
          <WorkingPrintButton />
          <Button variant="ghost" onClick={onReset}>Start again</Button>
        </div>
        <p className="mt-6 text-xs leading-5 text-stone-500">Planning draft only. Travel times, darshan arrangements and official rules should be verified before booking.</p>
      </div>
    </div>
  );
}

function ResultBlock({ icon: Icon, title, items }: { icon: React.ComponentType<{ className?: string }>; title: string; items: string[] }) {
  return <Card className="h-full border-gold/30"><CardContent className="p-5"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-orange-50 text-saffron"><Icon className="h-4 w-4" /></span><h3 className="font-bold">{title}</h3></div><ul className="mt-4 space-y-2">{items.map((item) => <li key={item} className="flex gap-2 text-sm leading-6 text-stone-600"><Sparkles className="mt-1 h-3.5 w-3.5 shrink-0 text-gold" />{item}</li>)}</ul></CardContent></Card>;
}

function buildResult(answers: Answers) {
  const days = String(answers.days || 1) as keyof typeof planner.plans;
  const rule = planner.plans[days] || planner.plans["1"];
  let base = answers.stayPreference !== "Not Sure" && answers.stayPreference ? answers.stayPreference : rule.base;
  if (answers.days === 7) base = answers.stayPreference === "Ujjain" ? "Split between Ujjain and Bhopal" : answers.stayPreference === "Not Sure" ? "Ujjain, Indore and Bhopal split" : base;
  if (answers.visitorType === "Elderly Parents" && answers.days && answers.days <= 3) base = "Ujjain";
  if (answers.startingCity === "Indore" && answers.stayPreference === "Not Sure" && answers.days === 1) base = "Ujjain";

  const itinerary = [...rule.itinerary];
  if (answers.interests.includes("Food") && answers.days && answers.days >= 3) itinerary.push("Add an evening Indore food trail with an early finish.");
  if (answers.interests.includes("Nature") && answers.days === 7) itinerary.push("Keep a slower lakefront window in Bhopal.");
  if (answers.interests.includes("Slow Travel")) itinerary.push("Keep one unscheduled half-day for rest, queues or a spontaneous local stop.");
  if (answers.interests.includes("Family Friendly")) itinerary.push("Schedule a hotel rest break after the longest darshan or transfer.");

  const temples = [...rule.temples];
  if (answers.interests.includes("Jyotirlinga Circuit") && !temples.includes("Omkareshwar")) temples.push("Omkareshwar");
  const nearby = [...rule.nearby];
  if (answers.interests.includes("Heritage") && answers.days && answers.days >= 5 && !nearby.includes("Mandu")) nearby.push("Mandu");
  const food = answers.visitorType === "International Visitor" ? planner.foods["International Visitor"] : answers.interests.includes("Food") ? planner.foods.Food : planner.foods.default;
  const elderlyTips = answers.visitorType === "Elderly Parents" || answers.interests.includes("Family Friendly") ? planner.elderlyTips : planner.elderlyTips.slice(0, 2);
  return { base, itinerary, temples, nearby, food, elderlyTips, travelTime: planner.routes[answers.startingCity as keyof typeof planner.routes] || planner.routes.Other };
}

function questionForStep(step: number) {
  return ["Where will your journey begin?", "How many days do you have?", "Who is travelling?", "Where would you prefer to stay?", "What would make this trip meaningful?"][step];
}
function helperForStep(step: number) {
  return ["This helps shape the route placeholder.", "Trip length determines the core circuit.", "We use this to adjust pace and accessibility tips.", "Choose a city, or let the planner recommend one.", "Select one or more interests."][step];
}
