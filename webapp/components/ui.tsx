import Link from "next/link";
import { ArrowRight, MessageCircle } from "lucide-react";

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-saffron">{children}</p>;
}

export function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body?: string }) {
  return (
    <div className="max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="font-serif text-3xl font-semibold leading-tight text-ink sm:text-4xl lg:text-5xl">{title}</h2>
      {body && <p className="mt-4 text-base leading-7 text-stone-600 sm:text-lg">{body}</p>}
    </div>
  );
}

export function CTA({ href, children, secondary = false }: { href: string; children: React.ReactNode; secondary?: boolean }) {
  return (
    <Link
      href={href}
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-bold transition hover:-translate-y-0.5 ${
        secondary ? "border border-stone-300 bg-white text-ink hover:border-saffron" : "bg-saffron text-white shadow-lg shadow-orange-900/15 hover:bg-[#d85b22]"
      }`}
    >
      {children} <ArrowRight className="h-4 w-4" />
    </Link>
  );
}

export function WhatsAppShare({ text }: { text: string }) {
  const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full bg-[#1f9d55] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#188248]">
      <MessageCircle className="h-4 w-4" /> Share on WhatsApp
    </a>
  );
}
