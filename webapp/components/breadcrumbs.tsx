import Link from "next/link";
import { ChevronRight, Home } from "lucide-react";

export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="border-b border-stone-200 bg-white">
      <ol className="mx-auto flex max-w-7xl items-center gap-2 overflow-x-auto px-4 py-3 text-xs text-stone-500 sm:px-6 lg:px-8">
        <li><Link href="/" aria-label="Home"><Home className="h-4 w-4" /></Link></li>
        {items.map((item) => <li key={item.label} className="flex items-center gap-2 whitespace-nowrap"><ChevronRight className="h-3 w-3" />{item.href ? <Link href={item.href}>{item.label}</Link> : <span className="font-semibold text-stone-700">{item.label}</span>}</li>)}
      </ol>
    </nav>
  );
}
