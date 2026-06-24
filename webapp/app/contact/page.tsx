import type { Metadata } from "next";
import { Mail, MessageCircle } from "lucide-react";
import { Eyebrow } from "@/components/ui";

export const metadata: Metadata = { title: "Contact & Enquiry" };
export default function ContactPage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-2">
        <div>
          <Eyebrow>We’re here to help</Eyebrow>
          <h1 className="font-serif text-5xl font-semibold leading-tight text-ink sm:text-6xl">Tell us about your journey.</h1>
          <p className="mt-5 max-w-lg text-lg leading-8 text-stone-600">Share your dates, group size and priorities. This enquiry form is frontend-ready and can be connected to your preferred email or CRM service.</p>
          <div className="mt-9 space-y-4 text-sm font-semibold text-stone-700"><p className="flex items-center gap-3"><Mail className="text-saffron" /> info@indiankumbh.com</p><p className="flex items-center gap-3"><Mail className="text-saffron" /> support@indiankumbh.com</p><p className="flex items-center gap-3"><MessageCircle className="text-[#1f9d55]" /> WhatsApp support placeholder</p></div>
        </div>
        <form className="rounded-[2rem] bg-white p-7 shadow-soft sm:p-9">
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="text-sm font-bold">Name<input required className="mt-2 h-12 w-full rounded-xl border border-stone-300 px-4 font-normal outline-none focus:border-saffron" /></label>
            <label className="text-sm font-bold">Email<input required type="email" className="mt-2 h-12 w-full rounded-xl border border-stone-300 px-4 font-normal outline-none focus:border-saffron" /></label>
            <label className="text-sm font-bold">Travel month<input type="month" className="mt-2 h-12 w-full rounded-xl border border-stone-300 px-4 font-normal outline-none focus:border-saffron" /></label>
            <label className="text-sm font-bold">Group size<input type="number" min="1" className="mt-2 h-12 w-full rounded-xl border border-stone-300 px-4 font-normal outline-none focus:border-saffron" /></label>
          </div>
          <label className="mt-5 block text-sm font-bold">How can we help?<textarea rows={5} className="mt-2 w-full rounded-xl border border-stone-300 p-4 font-normal outline-none focus:border-saffron" /></label>
          <button type="button" className="mt-6 w-full rounded-full bg-saffron px-6 py-4 text-sm font-bold text-white">Send enquiry</button>
          <p className="mt-3 text-center text-xs text-stone-400">Demo form — connect a form endpoint before launch.</p>
        </form>
      </div>
    </main>
  );
}
