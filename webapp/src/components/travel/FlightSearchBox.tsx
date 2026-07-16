import { TravelSearchWidget } from "./TravelSearchWidget";

export function FlightSearchBox({ sourcePage = "flight-search-box" }: { sourcePage?: string }) {
  return <TravelSearchWidget title="Search flights for your Kumbh trip" sourcePage={sourcePage} />;
}
