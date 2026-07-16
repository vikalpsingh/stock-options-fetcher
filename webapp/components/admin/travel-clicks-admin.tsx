"use client";

import { useMemo, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import type { TravelOutboundClick } from "@/src/lib/travel/outbound-clicks";
import { Button } from "@/components/ui/button";

export function TravelClicksAdmin({ initialClicks }: { initialClicks: TravelOutboundClick[] }) {
  const [filters, setFilters] = useState({ mode: "", provider: "", campaign: "", sourcePage: "", from: "", to: "" });
  const modes = unique(initialClicks.map((click) => click.mode));
  const providers = unique(initialClicks.map((click) => click.providerId));
  const campaigns = unique(initialClicks.map((click) => click.campaign).filter(Boolean) as string[]);
  const sourcePages = unique(initialClicks.map((click) => click.sourcePage).filter(Boolean) as string[]);
  const filtered = initialClicks.filter((click) =>
    (!filters.mode || click.mode === filters.mode) &&
    (!filters.provider || click.providerId === filters.provider) &&
    (!filters.campaign || click.campaign === filters.campaign) &&
    (!filters.sourcePage || click.sourcePage === filters.sourcePage) &&
    (!filters.from || click.fromCitySlug === filters.from) &&
    (!filters.to || click.toCitySlug === filters.to || click.citySlug === filters.to),
  );
  const summary = useMemo(() => summarize(filtered), [filtered]);

  return (
    <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px]">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Private analytics</p><h1 className="mt-2 font-serif text-4xl">Travel redirect clicks</h1><p className="mt-2 text-sm text-stone-600">{filtered.length} of {initialClicks.length} clicks shown</p></div>
          <div className="flex gap-2"><Button variant="outline" onClick={() => location.reload()}><RefreshCw className="h-4 w-4" />Refresh</Button><Button asChild><a href="/api/admin/travel-clicks/export"><Download className="h-4 w-4" />Export CSV</a></Button></div>
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-7">
          {Object.entries(summary).map(([label, value]) => <div key={label} className="rounded-3xl border border-gold/35 bg-white p-4"><p className="text-[10px] font-black uppercase tracking-wider text-saffron">{label}</p><p className="mt-2 text-2xl font-bold text-ink">{value || "—"}</p></div>)}
        </div>
        <div className="mt-8 grid gap-3 rounded-3xl border border-gold/35 bg-white p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Filter label="Mode" value={filters.mode} options={modes} onChange={(value) => setFilters((current) => ({ ...current, mode: value }))} />
          <Filter label="Provider" value={filters.provider} options={providers} onChange={(value) => setFilters((current) => ({ ...current, provider: value }))} />
          <Filter label="Campaign" value={filters.campaign} options={campaigns} onChange={(value) => setFilters((current) => ({ ...current, campaign: value }))} />
          <Filter label="Source page" value={filters.sourcePage} options={sourcePages} onChange={(value) => setFilters((current) => ({ ...current, sourcePage: value }))} />
        </div>
        <div className="mt-6 overflow-x-auto rounded-3xl border border-stone-200 bg-white shadow-soft">
          <table className="min-w-[1200px] w-full text-left text-sm">
            <thead className="bg-maroon text-xs uppercase tracking-wider text-white"><tr>{["Date", "Mode", "Provider", "From", "To / City", "Travel date", "Campaign", "Source page", "Target host"].map((h) => <th key={h} className="px-4 py-4">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-stone-200">
              {filtered.map((click) => <tr key={click.id}><td className="whitespace-nowrap px-4 py-4 text-xs text-stone-500">{new Date(click.createdAt).toLocaleString("en-IN")}</td><td className="px-4 py-4 font-bold">{click.mode}</td><td className="px-4 py-4">{click.providerId}</td><td className="px-4 py-4">{click.fromCitySlug || "—"}</td><td className="px-4 py-4">{click.toCitySlug || click.citySlug || "—"}</td><td className="px-4 py-4">{click.date || click.checkin || click.departureDate || "—"}</td><td className="px-4 py-4">{click.campaign || "—"}</td><td className="px-4 py-4">{click.sourcePage || "—"}</td><td className="px-4 py-4">{click.targetHost}</td></tr>)}
              {filtered.length === 0 && <tr><td colSpan={9} className="px-5 py-16 text-center text-stone-500">No clicks match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

function Filter({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="form-control normal-case tracking-normal text-ink"><option value="">All</option>{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}

function unique(values: string[]) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function summarize(clicks: TravelOutboundClick[]) {
  return {
    "Total clicks": clicks.length,
    "Bus clicks": clicks.filter((c) => c.mode === "bus").length,
    "Hotel clicks": clicks.filter((c) => c.mode === "hotel").length,
    "Flight clicks": clicks.filter((c) => c.mode === "flight").length,
    "Train clicks": clicks.filter((c) => c.mode === "train").length,
    "Top source": top(clicks.map((c) => c.fromCitySlug).filter(Boolean) as string[]),
    "Top provider": top(clicks.map((c) => c.providerId)),
  };
}

function top(values: string[]) {
  const counts = new Map<string, number>();
  values.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}
