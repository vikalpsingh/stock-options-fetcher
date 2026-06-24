"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Loader2, LockKeyhole, RefreshCw, Save } from "lucide-react";
import type { PackageEnquiry } from "@/lib/package-enquiries";
import { enquiryStatuses } from "@/lib/package-enquiry-types";
import { Button } from "@/components/ui/button";

type PartnerOption = { id: string; name: string; status: string };

export function AdminLogin({ configured }: { configured: boolean }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const response = await fetch("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    const result = await response.json() as { success?: boolean; error?: string };
    if (!response.ok) {
      setError(result.error || "Login failed.");
      setLoading(false);
      return;
    }
    router.refresh();
  }

  return (
    <main className="grid min-h-[70vh] place-items-center bg-cream px-4 py-16">
      <form onSubmit={login} className="w-full max-w-md rounded-[2rem] border border-gold/35 bg-white p-7 shadow-soft sm:p-9">
        <LockKeyhole className="h-10 w-10 text-maroon" />
        <h1 className="mt-5 font-serif text-3xl">Package enquiry admin</h1>
        <p className="mt-3 text-sm leading-6 text-stone-600">{configured ? "Enter the admin password to continue." : "Set ADMIN_PASSWORD in the server environment before using this dashboard."}</p>
        <label className="mt-6 block text-sm font-bold">Password<input required disabled={!configured} type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="form-control" /></label>
        {error && <p className="mt-4 rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-800">{error}</p>}
        <Button type="submit" className="mt-6 w-full" disabled={!configured || loading}>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}Login</Button>
      </form>
    </main>
  );
}

export function PackageEnquiriesAdmin({ initialEnquiries, partners }: { initialEnquiries: PackageEnquiry[]; partners: PartnerOption[] }) {
  const router = useRouter();
  const [enquiries, setEnquiries] = useState(initialEnquiries);
  const [filters, setFilters] = useState({ status: "", packageType: "", sourceCity: "", travelMonth: "" });
  const [savingId, setSavingId] = useState("");
  const packageTypes = useMemo(() => unique(enquiries.map((item) => item.packageType)), [enquiries]);
  const sourceCities = useMemo(() => unique(enquiries.map((item) => item.sourceCity)), [enquiries]);
  const travelMonths = useMemo(() => unique(enquiries.map((item) => item.travelMonth).filter(Boolean)), [enquiries]);
  const filtered = enquiries.filter((item) =>
    (!filters.status || item.status === filters.status) &&
    (!filters.packageType || item.packageType === filters.packageType) &&
    (!filters.sourceCity || item.sourceCity === filters.sourceCity) &&
    (!filters.travelMonth || item.travelMonth === filters.travelMonth),
  );

  function edit(id: string, key: "status" | "assignedPartnerId", value: string) {
    setEnquiries((current) => current.map((item) => item.id === id ? { ...item, [key]: key === "assignedPartnerId" ? value || null : value } as PackageEnquiry : item));
  }

  async function save(item: PackageEnquiry) {
    setSavingId(item.id);
    const response = await fetch("/api/admin/package-enquiries", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, status: item.status, assignedPartnerId: item.assignedPartnerId }),
    });
    setSavingId("");
    if (!response.ok) alert("Could not save this enquiry. Refresh and try again.");
  }

  return (
    <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px]">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Private operations</p><h1 className="mt-2 font-serif text-4xl">Package enquiries</h1><p className="mt-2 text-sm text-stone-600">{filtered.length} of {enquiries.length} enquiries shown</p></div>
          <div className="flex gap-2"><Button variant="outline" onClick={() => router.refresh()}><RefreshCw className="h-4 w-4" />Refresh</Button><Button asChild><a href="/api/admin/package-enquiries/export"><Download className="h-4 w-4" />Export CSV</a></Button></div>
        </div>

        <div className="mt-8 grid gap-3 rounded-3xl border border-gold/35 bg-white p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Filter label="Status" value={filters.status} options={enquiryStatuses} onChange={(value) => setFilters((current) => ({ ...current, status: value }))} />
          <Filter label="Package type" value={filters.packageType} options={packageTypes} onChange={(value) => setFilters((current) => ({ ...current, packageType: value }))} />
          <Filter label="Source city" value={filters.sourceCity} options={sourceCities} onChange={(value) => setFilters((current) => ({ ...current, sourceCity: value }))} />
          <Filter label="Travel month" value={filters.travelMonth} options={travelMonths} onChange={(value) => setFilters((current) => ({ ...current, travelMonth: value }))} />
        </div>

        <div className="mt-6 overflow-x-auto rounded-3xl border border-stone-200 bg-white shadow-soft">
          <table className="min-w-[1450px] w-full text-left text-sm">
            <thead className="bg-maroon text-xs uppercase tracking-wider text-white"><tr>{["Created", "Name", "Mobile", "Source city", "Travel month", "Package type", "Budget", "Status", "Assigned partner", "Action"].map((heading) => <th key={heading} className="px-4 py-4">{heading}</th>)}</tr></thead>
            <tbody className="divide-y divide-stone-200">
              {filtered.map((item) => <tr key={item.id} className="align-top"><td className="whitespace-nowrap px-4 py-4 text-xs text-stone-500">{new Date(item.createdAt).toLocaleString("en-IN")}</td><td className="px-4 py-4 font-bold">{item.fullName}</td><td className="px-4 py-4"><a href={`tel:+91${item.mobile}`} className="text-maroon">{item.mobile}</a></td><td className="px-4 py-4">{item.sourceCity}</td><td className="px-4 py-4">{item.travelMonth || "—"}</td><td className="max-w-64 px-4 py-4">{item.packageType}</td><td className="px-4 py-4">{item.budgetPerPerson || "—"}</td><td className="px-4 py-4"><select value={item.status} onChange={(event) => edit(item.id, "status", event.target.value)} className="h-10 rounded-xl border border-stone-300 bg-white px-3">{enquiryStatuses.map((status) => <option key={status}>{status}</option>)}</select></td><td className="px-4 py-4"><select value={item.assignedPartnerId || ""} onChange={(event) => edit(item.id, "assignedPartnerId", event.target.value)} className="h-10 max-w-56 rounded-xl border border-stone-300 bg-white px-3"><option value="">Unassigned</option>{partners.map((partner) => <option key={partner.id} value={partner.id}>{partner.name} ({partner.status})</option>)}</select></td><td className="px-4 py-4"><Button size="sm" onClick={() => save(item)} disabled={savingId === item.id}>{savingId === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save</Button></td></tr>)}
              {filtered.length === 0 && <tr><td colSpan={10} className="px-5 py-16 text-center text-stone-500">No enquiries match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

function Filter({ label, value, options, onChange }: { label: string; value: string; options: readonly string[]; onChange: (value: string) => void }) {
  return <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="form-control normal-case tracking-normal text-ink"><option value="">All</option>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>;
}

function unique(values: string[]) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}
