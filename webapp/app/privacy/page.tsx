import type { Metadata } from "next";
import Link from "next/link";
import { Mail, ShieldCheck } from "lucide-react";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How IndianKumbh.com handles travel enquiries, analytics and partner referrals.",
  alternates: { canonical: "/privacy" },
};

const sections = [
  ["Information we collect", "When you submit a package enquiry, we may collect your name, mobile and WhatsApp numbers, email, source city, travel month, group details, budget, stay preference and requested services. We may also store source-page and campaign information, browser user agent and operational status."],
  ["How we use information", "We use enquiry information to respond to you, understand your trip, improve the website, prevent duplicate or spam submissions, and connect you with relevant verified travel partners when you have provided consent."],
  ["Sharing with travel partners", "We share only information relevant to your request and only with partners considered suitable for the requested destination or service. Partners operate independently and apply their own booking and privacy terms."],
  ["Affiliate links and analytics", "Some hotel or travel links may be affiliate links. We may record a non-sensitive click event such as the campaign, destination, referring page and browser user agent. Partner websites may use their own cookies and tracking technologies."],
  ["Storage and retention", "Phase-1 enquiries are stored on the IndianKumbh server for operational follow-up. We retain records only as long as reasonably needed for enquiry handling, fraud prevention, reporting and legal obligations."],
  ["Your choices", "You may ask us to correct or delete your enquiry information, or withdraw permission for future partner contact, by emailing support@indiankumbh.com. We may need to retain limited records where required for security or legal compliance."],
  ["Security", "We use reasonable access controls and operational safeguards, but no internet service can guarantee absolute security. Do not send payment card details, passwords, government identity documents or medical records through an enquiry form."],
  ["Children", "Package enquiries should be submitted by an adult. Group information about children should be limited to the number of children and practical travel requirements."],
];

export default function PrivacyPage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl">
        <p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Trust & data</p>
        <h1 className="mt-3 font-serif text-5xl font-semibold sm:text-6xl">Privacy Policy</h1>
        <p className="mt-5 text-lg leading-8 text-stone-600">This policy explains how IndianKumbh.com handles information submitted through travel planning and package enquiry features.</p>
        <div className="mt-8 flex gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-sm leading-6 text-emerald-950"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" /><p>IndianKumbh.com does not request or process package payments. Never send payment credentials through our forms or email.</p></div>
        <div className="mt-10 space-y-5">{sections.map(([title, text]) => <section key={title} className="rounded-3xl border border-gold/30 bg-white p-6 sm:p-8"><h2 className="font-serif text-2xl">{title}</h2><p className="mt-3 leading-7 text-stone-600">{text}</p></section>)}</div>
        <div className="mt-8 rounded-3xl bg-maroon p-6 text-white sm:p-8"><h2 className="font-serif text-2xl text-white">Contact us about privacy</h2><p className="mt-3 flex items-center gap-2 text-sm text-orange-50/85"><Mail className="h-4 w-4 text-gold" />support@indiankumbh.com</p><p className="mt-4 text-xs text-orange-50/60">Last updated: June 21, 2026</p></div>
        <p className="mt-8 text-sm text-stone-600">Also read our <Link href="/disclaimer" className="font-bold text-maroon underline">travel and package disclaimer</Link>.</p>
      </div>
    </main>
  );
}

