import type { TripPlannerInput, TripRecommendation } from "./trip-planner";

export const feedbackOptions = [
  "Cheaper hotels needed",
  "Dharamshala / ashram stay needed",
  "Train information needed",
  "Bus options missing",
  "Senior citizen help needed",
  "Mahakal darshan help needed",
  "Local transport needed",
  "Parking information needed",
  "Food guide needed",
  "Other",
] as const;

export type FeedbackOption = (typeof feedbackOptions)[number];

export type TripSubmissionRecord = {
  id: string;
  createdAt: string;
  input: TripPlannerInput;
  recommendation: TripRecommendation;
};

export type FeedbackRecord = {
  id: string;
  submissionId: string;
  createdAt: string;
  useful: boolean;
  options: FeedbackOption[];
  otherText?: string;
};

export interface PlannerStorageAdapter {
  saveSubmission(record: TripSubmissionRecord): void;
  saveFeedback(record: FeedbackRecord): void;
}

const submissionKey = "indiankumbh.tripPlanner.submissions.v1";
const feedbackKey = "indiankumbh.tripPlanner.feedback.v1";

class BrowserJsonStorageAdapter implements PlannerStorageAdapter {
  saveSubmission(record: TripSubmissionRecord) {
    appendRecord(submissionKey, record);
  }

  saveFeedback(record: FeedbackRecord) {
    appendRecord(feedbackKey, record);
  }
}

const browserStorage = new BrowserJsonStorageAdapter();

export function saveTripSubmission(input: TripPlannerInput, recommendation: TripRecommendation) {
  const record: TripSubmissionRecord = {
    id: createId(),
    createdAt: new Date().toISOString(),
    input,
    recommendation,
  };
  browserStorage.saveSubmission(record);
  return record;
}

export function saveTripFeedback(input: Omit<FeedbackRecord, "id" | "createdAt">) {
  const record: FeedbackRecord = {
    id: createId(),
    createdAt: new Date().toISOString(),
    ...input,
  };
  browserStorage.saveFeedback(record);
  return record;
}

function appendRecord<T>(key: string, record: T) {
  if (typeof window === "undefined") return;
  try {
    const existing = JSON.parse(window.localStorage.getItem(key) || "[]") as T[];
    const next = [...existing, record].slice(-100);
    window.localStorage.setItem(key, JSON.stringify(next));
  } catch {
    try {
      window.localStorage.setItem(key, JSON.stringify([record]));
    } catch {
      // Storage can be disabled or full. The planner must still return a result.
    }
  }
}

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `trip_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}
