import { localeCodes } from "@/lib/locale";

export function generateStaticParams() {
  return ["en", ...localeCodes].map((locale) => ({ locale }));
}

export default function LocaleLayout({ children }: { children: React.ReactNode }) {
  return children;
}
