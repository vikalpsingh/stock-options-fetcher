import { ShieldCheck } from "lucide-react";
import { getEditorialSource } from "@/src/data/editorialSources";

export function VerificationNote({ sourceId, className = "", context = "general" }: { sourceId?: string; className?: string; context?: "general" | "char-dham" | "jyotirlinga" }) {
  const source = getEditorialSource(sourceId);
  const extra = context === "char-dham"
    ? "Char Dham registration, vehicle registration, health registration and helicopter booking should be checked through official Uttarakhand portals."
    : context === "jyotirlinga"
      ? "Darshan timings, special aarti bookings and crowd rules vary by temple and festival season. Check official temple sources before travel."
      : "";
  return (
    <div className={`rounded-3xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950 ${className}`}>
      <div className="flex gap-3">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
        <div>
          <p className="font-bold">Verification status: {source?.reliability || "medium"} editorial planning note</p>
          <p className="mt-1">Last updated: {source?.lastChecked || "2026-07-15"}</p>
          <p className="mt-2">Temple timings, registration rules, route status, weather alerts, helicopter booking, darshan booking, transport availability and local services can change. Please verify with official government or temple sources before booking travel.</p>
          {extra && <p className="mt-2 font-semibold">{extra}</p>}
          {source?.notes && <p className="mt-2 text-xs text-amber-800">{source.notes}</p>}
        </div>
      </div>
    </div>
  );
}
