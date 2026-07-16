export type CharDhamStop = {
  slug: string;
  templeName: string;
  state: string;
  altitude: string;
  openingSeason: string;
  difficulty: "easy" | "moderate" | "difficult";
  nearestBaseTown: string;
  registrationRequired: boolean;
  helicopterAvailable: boolean;
  seniorCitizenNotes: string;
  shortDescription: string;
};

export const charDhamStops: CharDhamStop[] = [
  { slug: "yamunotri", templeName: "Yamunotri", state: "Uttarakhand", altitude: "Approx. 3,293 m", openingSeason: "Usually summer to autumn, subject to official temple schedule", difficulty: "difficult", nearestBaseTown: "Barkot / Janki Chatti", registrationRequired: true, helicopterAvailable: false, seniorCitizenNotes: "Requires careful walking/pony/palki planning from Janki Chatti. Avoid rushing on the first high-altitude day.", shortDescription: "The Yamuna source pilgrimage and usual first stop of Char Dham Yatra." },
  { slug: "gangotri", templeName: "Gangotri", state: "Uttarakhand", altitude: "Approx. 3,100 m", openingSeason: "Usually summer to autumn, subject to official temple schedule", difficulty: "moderate", nearestBaseTown: "Uttarkashi / Harsil", registrationRequired: true, helicopterAvailable: false, seniorCitizenNotes: "Road access is easier than Yamunotri/Kedarnath, but altitude, cold and long drives need buffers.", shortDescription: "A high Himalayan temple associated with Maa Ganga." },
  { slug: "kedarnath", templeName: "Kedarnath", state: "Uttarakhand", altitude: "Approx. 3,583 m", openingSeason: "Usually summer to autumn, subject to weather and official schedule", difficulty: "difficult", nearestBaseTown: "Sonprayag / Gaurikund", registrationRequired: true, helicopterAvailable: true, seniorCitizenNotes: "Most demanding Char Dham stop. Consider medical check, helicopter options, rest days and oxygen/altitude awareness.", shortDescription: "High-altitude Shiva temple and Jyotirlinga requiring serious preparation." },
  { slug: "badrinath", templeName: "Badrinath", state: "Uttarakhand", altitude: "Approx. 3,133 m", openingSeason: "Usually summer to autumn, subject to official temple schedule", difficulty: "moderate", nearestBaseTown: "Joshimath / Badrinath", registrationRequired: true, helicopterAvailable: false, seniorCitizenNotes: "Road-based access with altitude exposure. Keep rest time in Joshimath/Badrinath and avoid night hill travel.", shortDescription: "A major Vishnu pilgrimage and usual final stop of Char Dham Yatra." },
];

export function getCharDhamStop(slug: string) {
  return charDhamStops.find((stop) => stop.slug === slug);
}
