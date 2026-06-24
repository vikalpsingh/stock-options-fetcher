import type { Metadata } from "next";
import { NationalKumbhHome } from "@/components/kumbh-portal";

export const metadata: Metadata = {
  title: "IndianKumbh — Trusted Guides for Every Kumbh Mela in India",
  description: "Plan Ujjain Simhastha 2028 and explore growing guides for Nashik-Trimbakeshwar, Prayagraj and Haridwar Kumbh Melas.",
  keywords: ["Indian Kumbh", "Ujjain Simhastha 2028", "Nashik Kumbh 2027", "Prayagraj Kumbh", "Haridwar Kumbh"],
  alternates: { canonical: "/" },
  openGraph: { title: "IndianKumbh — One Trusted Guide for All Kumbh Melas", description: "Currently focused on Ujjain Simhastha 2028, with national Kumbh guides being built.", images: ["/images/mahakal-ghat-temple.png"] },
};

export default function HomePage() {
  return <NationalKumbhHome />;
}
