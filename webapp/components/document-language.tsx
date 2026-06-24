"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { getPathLocale } from "@/lib/locale";

export function DocumentLanguage() {
  const pathname = usePathname();
  useEffect(() => {
    document.documentElement.lang = getPathLocale(pathname);
  }, [pathname]);
  return null;
}
