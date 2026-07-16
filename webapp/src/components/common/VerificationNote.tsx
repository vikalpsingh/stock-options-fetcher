import { ShieldCheck } from "lucide-react";
import { getEditorialSource } from "@/src/data/editorialSources";

export function VerificationNote({ sourceId, className = "" }: { sourceId: string; className?: string }) {
  const source = getEditorialSource(sourceId);
  return (
    <div className={`rounded-3xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950 ${className}`}>
      <div className="flex gap-3">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
        <div>
          <p className="font-bold">Verification status: {source?.reliability || "medium"} editorial planning note</p>
          <p className="mt-1">Last updated: {source?.lastChecked || "2026-07-15"}</p>
          <p className="mt-2">Dates, bathing schedules, traffic rules and official services can change. Please verify with official government or temple sources before booking travel.</p>
          {source?.notes && <p className="mt-2 text-xs text-amber-800">{source.notes}</p>}
        </div>
      </div>
    </div>
  );
}
