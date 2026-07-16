import { TravelSearchWidget } from "./TravelSearchWidget";

export function TrainSearchBox({ sourcePage = "train-search-box" }: { sourcePage?: string }) {
  return <TravelSearchWidget title="Check trains for your Kumbh trip" sourcePage={sourcePage} />;
}
