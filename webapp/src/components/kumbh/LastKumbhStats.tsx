import { BarChart3, Building2, CheckCircle2, Users } from "lucide-react";
import type { ComponentType } from "react";
import { Card, CardContent } from "@/components/ui/card";

export function LastKumbhStats({
  previousEventYear,
  estimatedVisitors,
  duration,
  infrastructureBudget,
  keyLearnings,
  travellerTakeaways,
  sourceNote,
  confidenceLevel,
}: {
  destinationSlug: string;
  previousEventYear: string;
  estimatedVisitors: string;
  duration: string;
  infrastructureBudget?: string;
  keyLearnings: string[];
  travellerTakeaways: string[];
  sourceNote: string;
  confidenceLevel: "official" | "media_estimate" | "editorial_estimate";
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-4">
      <StatCard icon={BarChart3} title={`Previous event: ${previousEventYear}`} text={duration} />
      <StatCard icon={Users} title="Visitor scale" text={estimatedVisitors} />
      <StatCard icon={Building2} title="Infrastructure and services" text={infrastructureBudget || "Water, sanitation, medical, security and transport planning are key."} />
      <StatCard icon={CheckCircle2} title="Confidence" text={confidenceLevel.replaceAll("_", " ")} />
      <Card className="border-gold/35 lg:col-span-2"><CardContent><h3 className="font-serif text-2xl">Key learnings</h3><ul className="mt-4 space-y-2 text-sm leading-6 text-stone-600">{keyLearnings.map((item) => <li key={item}>• {item}</li>)}</ul></CardContent></Card>
      <Card className="border-gold/35 lg:col-span-2"><CardContent><h3 className="font-serif text-2xl">Traveller takeaways</h3><ul className="mt-4 space-y-2 text-sm leading-6 text-stone-600">{travellerTakeaways.map((item) => <li key={item}>• {item}</li>)}</ul><p className="mt-5 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-900">{sourceNote}</p></CardContent></Card>
    </div>
  );
}

function StatCard({ icon: Icon, title, text }: { icon: ComponentType<{ className?: string }>; title: string; text: string }) {
  return <Card className="border-gold/35 bg-[#fffdf8]"><CardContent><Icon className="h-6 w-6 text-saffron" /><h3 className="mt-4 font-serif text-xl">{title}</h3><p className="mt-2 text-sm leading-6 text-stone-600">{text}</p></CardContent></Card>;
}
