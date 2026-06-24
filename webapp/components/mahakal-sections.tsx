import Image from "next/image";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Droplets,
  Flame,
  Footprints,
  HeartHandshake,
  Landmark,
  MoonStar,
  ShieldCheck,
  Sparkles,
  SunMedium,
  TicketCheck,
  Users,
} from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

const darshanIcons = { users: Users, sparkles: Sparkles, ticket: TicketCheck, warning: AlertTriangle };

export function MahakalHero() {
  return (
    <section className="temple-silhouette relative overflow-hidden bg-maroon text-white">
      <Image
        src="/images/mahakal-temple-exterior.png"
        alt="Exterior view of Mahakaleshwar temple complex in Ujjain"
        fill
        priority
        className="object-cover object-[65%_center] sm:object-center"
        sizes="100vw"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-[#240b0d]/95 via-[#50171b]/78 to-[#50171b]/25" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#280d0f]/75 via-transparent to-black/20" />
      <div className="pattern-mandala absolute inset-0 opacity-10" />
      <div className="relative mx-auto grid min-h-[580px] max-w-7xl items-center gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[1fr_.6fr] lg:px-8">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[.2em] text-gold"><Flame className="h-4 w-4" />Mahakal Guide</p>
          <h1 className="text-balance mt-6 font-serif text-5xl leading-[1.04] text-white sm:text-6xl">Mahakaleshwar Temple Guide for Ujjain Visitors</h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-orange-50/80">Darshan tips, Bhasma Aarti guidance, nearby temples, family-friendly planning, and route suggestions.</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href="/plan-my-trip?focus=mahakal">Plan Mahakal Visit <ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href="#nearby-temples">View Nearby Temples <Landmark className="h-4 w-4" /></Link></Button></div>
        </div>
        <div className="mx-auto hidden aspect-square w-full max-w-sm place-items-center rounded-full border border-gold/35 bg-black/20 shadow-2xl backdrop-blur-sm lg:grid">
          <div className="grid h-48 w-48 place-items-center rounded-full border border-white/20 bg-maroon/35 text-center"><span className="font-serif text-7xl text-gold">ॐ</span></div>
        </div>
      </div>
    </section>
  );
}

export function DarshanPlanningCard({ item }: { item: { title: string; description: string; bestFor: string; icon: string } }) {
  const Icon = darshanIcons[item.icon as keyof typeof darshanIcons] ?? ShieldCheck;
  return (
    <Card className="h-full border-t-4 border-t-gold">
      <CardContent>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span>
        <h3 className="mt-5 font-serif text-2xl">{item.title}</h3>
        <p className="mt-3 text-sm leading-6 text-stone-600">{item.description}</p>
        <p className="mt-5 border-t border-stone-200 pt-4 text-xs"><strong className="text-maroon">Best for:</strong> {item.bestFor}</p>
        <p className="mt-3 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-900">Timings should be verified from official temple sources before travel.</p>
      </CardContent>
    </Card>
  );
}

export function BhasmaAartiTimeline({ steps }: { steps: { title: string; description: string }[] }) {
  return (
    <div className="overflow-hidden rounded-[2rem] border border-gold/40 bg-white shadow-soft">
      <div className="relative overflow-hidden p-7 text-white sm:p-10">
        <Image src="/images/mahakal-sanctum.png" alt="" fill className="object-cover object-center" sizes="(max-width: 1280px) 100vw, 1280px" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#240b0d]/95 via-[#641f26]/82 to-[#641f26]/45" />
        <div className="pattern-mandala absolute inset-0 opacity-10" />
        <div className="relative flex items-center gap-3"><MoonStar className="h-7 w-7 text-gold" /><div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-gold">Step-by-step</p><h3 className="mt-1 font-serif text-3xl text-white">Bhasma Aarti preparation</h3></div></div>
      </div>
      <ol className="grid p-6 sm:p-8 lg:grid-cols-5">
        {steps.map((step, index) => <li key={step.title} className="relative border-l border-gold/40 pb-8 pl-8 last:pb-0 lg:border-l-0 lg:border-t lg:pb-0 lg:pl-0 lg:pt-8"><span className="absolute -left-3 top-0 grid h-6 w-6 place-items-center rounded-full bg-saffron text-xs font-bold text-white ring-4 ring-orange-50 lg:-top-3 lg:left-0">{index + 1}</span><div className="lg:pr-5"><h4 className="font-bold text-ink">{step.title}</h4><p className="mt-2 text-sm leading-6 text-stone-600">{step.description}</p></div></li>)}
      </ol>
    </div>
  );
}

const tipIcons = [SunMedium, Droplets, HeartHandshake, Footprints, Clock3];
export function FamilyTipCards({ tips }: { tips: { title: string; description: string }[] }) {
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{tips.map((tip, index) => { const Icon = tipIcons[index] || CheckCircle2; return <Card key={tip.title} className="h-full border-gold/35 bg-[#fffaf0]"><CardContent><Icon className="h-6 w-6 text-saffron" /><h3 className="mt-4 font-bold">{tip.title}</h3><p className="mt-2 text-sm leading-6 text-stone-600">{tip.description}</p></CardContent></Card>; })}</div>;
}

export function TemplePlanCard({ plan, index }: { plan: { title: string; duration: string; steps: string[] }; index: number }) {
  return <Card className="h-full overflow-hidden"><div className={`${index === 0 ? "bg-saffron" : "bg-maroon"} temple-silhouette p-6 text-white`}><p className="text-xs font-bold uppercase tracking-widest text-orange-100">{plan.duration}</p><h3 className="mt-2 font-serif text-3xl text-white">{plan.title}</h3></div><CardContent><ol className="space-y-4">{plan.steps.map((step, stepIndex) => <li key={step} className="flex gap-3 text-sm leading-6 text-stone-700"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-orange-50 text-xs font-bold text-saffron">{stepIndex + 1}</span>{step}</li>)}</ol><Button asChild variant="outline" className="mt-6 w-full"><Link href="/plan-my-trip?focus=temple-circuit">Use this plan</Link></Button></CardContent></Card>;
}
