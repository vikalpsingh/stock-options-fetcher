export type PlannerAnalyticsEvent =
  | "trip_form_submitted"
  | "travel_cta_clicked"
  | "hotel_cta_clicked"
  | "feedback_submitted";

declare global {
  interface Window {
    dataLayer?: Record<string, unknown>[];
  }
}

export function trackPlannerEvent(event: PlannerAnalyticsEvent, properties: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({ event, ...properties });
}

