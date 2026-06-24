import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { IllustratedRouteCard, RoutePlanningTimeline } from "@/components/content-visuals";
import { HeroSection, SectionTitle } from "@/components/travel-components";
import routes from "@/data/routes.json";

export const metadata: Metadata = {
  title: "How to Reach Ujjain by Flight, Train and Road",
  description: "Compare practical routes to Ujjain from Indore, Bhopal, Delhi, Mumbai, Ahmedabad and Bengaluru, with Maps links and family travel guidance.",
  alternates: { canonical: "/how-to-reach" },
};

export default function HowToReachPage() {
  return (
    <main>
      <Breadcrumbs items={[{ label: "How to Reach Ujjain" }]} />
      <HeroSection compact eyebrow="Routes & arrival planning" title="How to Reach" accent="Ujjain" description="Compare flight, train and road approaches, then save a practical route for your family. Travel times remain planning estimates until verified for your date." />
      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionTitle eyebrow="Route options" title="Choose the arrival that matches your group" description="Indore is the most common air gateway, while direct trains can reduce road transfers during busy periods." />
          <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {routes.map((route) => <IllustratedRouteCard key={route.id} route={route} />)}
          </div>
        </div>
      </section>
      <section className="pattern-jaali bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-4xl"><RoutePlanningTimeline /></div>
      </section>
    </main>
  );
}
