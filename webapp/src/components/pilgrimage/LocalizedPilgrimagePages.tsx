import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, Languages, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { LocaleCode } from "@/lib/locale";
import { localizedHref } from "@/lib/locale";
import { charDhamGuides, getCharDhamGuide } from "@/src/data/charDhamGuides";
import { jyotirlingaGuides, getJyotirlingaGuide } from "@/src/data/jyotirlingaGuides";
import { getKumbhGuide, kumbhGuides } from "@/src/data/kumbhGuides";

type Pillar = "kumbh" | "char-dham" | "jyotirlinga";

type LocalCopy = {
  languageLabel: string;
  planTravel: string;
  packageQuote: string;
  readGuide: string;
  verify: string;
  sections: string;
  quickFacts: string;
  importantPlaces: string;
  familySenior: string;
  allGuides: string;
  kumbhTitle: string;
  kumbhDescription: string;
  charTitle: string;
  charDescription: string;
  jyotiTitle: string;
  jyotiDescription: string;
  currentFocus: string;
  nextFocus: string;
  services: string;
  history: string;
  stay: string;
  reach: string;
  faqs: string;
  packages: string;
};

const copy: Record<LocaleCode, LocalCopy> = {
  hi: {
    languageLabel: "हिन्दी", planTravel: "यात्रा योजना", packageQuote: "पैकेज कोट", readGuide: "गाइड पढ़ें", sections: "उपयोगी अनुभाग", quickFacts: "मुख्य तथ्य", importantPlaces: "महत्वपूर्ण स्थान", familySenior: "परिवार और वरिष्ठ नागरिक सुझाव", allGuides: "सभी गाइड",
    verify: "तिथियां, मंदिर समय, पंजीकरण, मार्ग, मौसम और स्थानीय सेवाएं बदल सकती हैं। यात्रा बुक करने से पहले सरकारी या मंदिर के आधिकारिक स्रोतों से पुष्टि करें।",
    kumbhTitle: "कुंभ मेला गाइड", kumbhDescription: "नासिक कुंभ 2027, उज्जैन सिंहस्थ 2028, प्रयागराज और हरिद्वार कुंभ के लिए व्यावहारिक यात्रा जानकारी।",
    charTitle: "चार धाम यात्रा गाइड", charDescription: "यमुनोत्री, गंगोत्री, केदारनाथ और बद्रीनाथ के लिए पंजीकरण, मार्ग, स्वास्थ्य, ठहराव और वरिष्ठ नागरिक योजना।",
    jyotiTitle: "12 ज्योतिर्लिंग दर्शन गाइड", jyotiDescription: "भारत के 12 ज्योतिर्लिंगों को क्षेत्रवार, परिवार और वरिष्ठ नागरिकों के अनुकूल तरीके से योजना बनाएं।",
    currentFocus: "वर्तमान फोकस", nextFocus: "अगला प्रमुख फोकस", services: "सेवाएं", history: "इतिहास", stay: "ठहरना", reach: "कैसे पहुंचें", faqs: "प्रश्न", packages: "पैकेज",
  },
  bn: {
    languageLabel: "বাংলা", planTravel: "ভ্রমণ পরিকল্পনা", packageQuote: "প্যাকেজ কোট", readGuide: "গাইড পড়ুন", sections: "প্রয়োজনীয় বিভাগ", quickFacts: "দ্রুত তথ্য", importantPlaces: "গুরুত্বপূর্ণ স্থান", familySenior: "পরিবার ও প্রবীণদের টিপস", allGuides: "সব গাইড",
    verify: "তারিখ, মন্দিরের সময়, নিবন্ধন, রুট, আবহাওয়া ও স্থানীয় পরিষেবা বদলাতে পারে। বুকিংয়ের আগে সরকারি বা মন্দিরের অফিসিয়াল সূত্রে যাচাই করুন।",
    kumbhTitle: "কুম্ভ মেলা গাইড", kumbhDescription: "নাশিক কুম্ভ ২০২৭, উজ্জয়িনী সিমহস্থ ২০২৮, প্রয়াগরাজ ও হরিদ্বার কুম্ভের ব্যবহারিক ভ্রমণ তথ্য।",
    charTitle: "চার ধাম যাত্রা গাইড", charDescription: "যমুনোত্রী, গঙ্গোত্রী, কেদারনাথ ও বদ্রিনাথের নিবন্ধন, রুট, স্বাস্থ্য, থাকা ও প্রবীণ ভ্রমণ পরিকল্পনা।",
    jyotiTitle: "১২ জ্যোতির্লিঙ্গ দর্শন গাইড", jyotiDescription: "ভারতের ১২ জ্যোতির্লিঙ্গকে অঞ্চলভিত্তিক, পরিবার ও প্রবীণ-বান্ধব ভাবে পরিকল্পনা করুন।",
    currentFocus: "বর্তমান ফোকাস", nextFocus: "পরবর্তী বড় ফোকাস", services: "পরিষেবা", history: "ইতিহাস", stay: "থাকা", reach: "কীভাবে যাবেন", faqs: "প্রশ্ন", packages: "প্যাকেজ",
  },
  mr: {
    languageLabel: "मराठी", planTravel: "प्रवास योजना", packageQuote: "पॅकेज कोट", readGuide: "गाइड वाचा", sections: "उपयुक्त विभाग", quickFacts: "महत्त्वाची माहिती", importantPlaces: "महत्त्वाची ठिकाणे", familySenior: "कुटुंब व ज्येष्ठांसाठी सूचना", allGuides: "सर्व गाइड",
    verify: "तारखा, मंदिर वेळा, नोंदणी, मार्ग, हवामान आणि स्थानिक सेवा बदलू शकतात. बुकिंगपूर्वी अधिकृत सरकारी किंवा मंदिर स्रोतांवर तपासा.",
    kumbhTitle: "कुंभ मेळा गाइड", kumbhDescription: "नाशिक कुंभ 2027, उज्जैन सिंहस्थ 2028, प्रयागराज आणि हरिद्वार कुंभसाठी व्यावहारिक प्रवास माहिती.",
    charTitle: "चार धाम यात्रा गाइड", charDescription: "यमुनोत्री, गंगोत्री, केदारनाथ आणि बद्रीनाथसाठी नोंदणी, मार्ग, आरोग्य, निवास आणि ज्येष्ठ नागरिक नियोजन.",
    jyotiTitle: "12 ज्योतिर्लिंग दर्शन गाइड", jyotiDescription: "भारताच्या 12 ज्योतिर्लिंगांना विभागानुसार, कुटुंब आणि ज्येष्ठांसाठी सोप्या पद्धतीने योजना करा.",
    currentFocus: "सध्याचा फोकस", nextFocus: "पुढील प्रमुख फोकस", services: "सेवा", history: "इतिहास", stay: "निवास", reach: "कसे पोहोचाल", faqs: "प्रश्न", packages: "पॅकेज",
  },
  te: {
    languageLabel: "తెలుగు", planTravel: "ప్రయాణ ప్రణాళిక", packageQuote: "ప్యాకేజ్ కోట్", readGuide: "గైడ్ చదవండి", sections: "ఉపయోగకర విభాగాలు", quickFacts: "త్వరిత విషయాలు", importantPlaces: "ముఖ్యమైన ప్రదేశాలు", familySenior: "కుటుంబం మరియు వృద్ధుల సూచనలు", allGuides: "అన్ని గైడ్లు",
    verify: "తేదీలు, ఆలయ సమయాలు, నమోదు, మార్గాలు, వాతావరణం మరియు స్థానిక సేవలు మారవచ్చు. బుకింగ్‌కు ముందు అధికారిక ప్రభుత్వ లేదా ఆలయ వనరులతో ధృవీకరించండి.",
    kumbhTitle: "కుంభ మేళా గైడ్", kumbhDescription: "నాసిక్ కుంభం 2027, ఉజ్జయిని సింహస్థ 2028, ప్రయాగ్‌రాజ్ మరియు హరిద్వార్ కుంభానికి ఉపయోగకర ప్రయాణ సమాచారం.",
    charTitle: "చార్ ధామ్ యాత్ర గైడ్", charDescription: "యమునోత్రి, గంగోత్రి, కేదార్నాథ్ మరియు బద్రీనాథ్ కోసం నమోదు, మార్గం, ఆరోగ్యం, వసతి మరియు వృద్ధుల ప్రణాళిక.",
    jyotiTitle: "12 జ్యోతిర్లింగ దర్శన గైడ్", jyotiDescription: "భారతదేశంలోని 12 జ్యోతిర్లింగాలను ప్రాంతాల వారీగా కుటుంబం మరియు వృద్ధులకు అనుకూలంగా ప్లాన్ చేయండి.",
    currentFocus: "ప్రస్తుత ఫోకస్", nextFocus: "తదుపరి ప్రధాన ఫోకస్", services: "సేవలు", history: "చరిత్ర", stay: "వసతి", reach: "ఎలా చేరాలి", faqs: "ప్రశ్నలు", packages: "ప్యాకేజీలు",
  },
  ta: {
    languageLabel: "தமிழ்", planTravel: "பயணத் திட்டம்", packageQuote: "பேக்கேஜ் கோட்", readGuide: "வழிகாட்டி படிக்க", sections: "பயனுள்ள பிரிவுகள்", quickFacts: "முக்கிய தகவல்கள்", importantPlaces: "முக்கிய இடங்கள்", familySenior: "குடும்பம் மற்றும் முதியோருக்கான குறிப்புகள்", allGuides: "அனைத்து வழிகாட்டிகள்",
    verify: "தேதிகள், கோவில் நேரம், பதிவு, வழிகள், வானிலை மற்றும் உள்ளூர் சேவைகள் மாறலாம். பயணம் பதிவு செய்வதற்கு முன் அரசு அல்லது கோவில் அதிகாரப்பூர்வ ஆதாரங்களில் சரிபார்க்கவும்.",
    kumbhTitle: "கும்பமேளா வழிகாட்டி", kumbhDescription: "நாசிக் கும்பம் 2027, உஜ்ஜைன் சிம்ஹஸ்தா 2028, பிரயாக்ராஜ் மற்றும் ஹரித்வார் கும்பத்திற்கான நடைமுறை பயண தகவல்.",
    charTitle: "சார் தாம் யாத்திரை வழிகாட்டி", charDescription: "யமுனோத்ரி, கங்கோத்ரி, கேதார்நாத் மற்றும் பத்ரிநாத் பயணத்திற்கு பதிவு, பாதை, உடல்நலம், தங்குமிடம் மற்றும் முதியோர் திட்டம்.",
    jyotiTitle: "12 ஜோதிர்லிங்க தரிசன வழிகாட்டி", jyotiDescription: "இந்தியாவின் 12 ஜோதிர்லிங்கங்களை பிராந்திய வாரியாக குடும்பம் மற்றும் முதியோருக்கு ஏற்றபடி திட்டமிடுங்கள்.",
    currentFocus: "தற்போதைய கவனம்", nextFocus: "அடுத்த முக்கிய கவனம்", services: "சேவைகள்", history: "வரலாறு", stay: "தங்குமிடம்", reach: "எப்படி செல்வது", faqs: "கேள்விகள்", packages: "பேக்கேஜ்கள்",
  },
  kn: {
    languageLabel: "ಕನ್ನಡ", planTravel: "ಪ್ರಯಾಣ ಯೋಜನೆ", packageQuote: "ಪ್ಯಾಕೇಜ್ ಕೋಟ್", readGuide: "ಗೈಡ್ ಓದಿ", sections: "ಉಪಯುಕ್ತ ವಿಭಾಗಗಳು", quickFacts: "ಮುಖ್ಯ ಮಾಹಿತಿ", importantPlaces: "ಮುಖ್ಯ ಸ್ಥಳಗಳು", familySenior: "ಕುಟುಂಬ ಮತ್ತು ಹಿರಿಯರ ಸಲಹೆಗಳು", allGuides: "ಎಲ್ಲಾ ಗೈಡ್ಗಳು",
    verify: "ದಿನಾಂಕಗಳು, ದೇವಸ್ಥಾನ ಸಮಯ, ನೋಂದಣಿ, ಮಾರ್ಗಗಳು, ಹವಾಮಾನ ಮತ್ತು ಸ್ಥಳೀಯ ಸೇವೆಗಳು ಬದಲಾಗಬಹುದು. ಬುಕ್ಕಿಂಗ್ ಮೊದಲು ಅಧಿಕೃತ ಸರ್ಕಾರಿ ಅಥವಾ ದೇವಸ್ಥಾನ ಮೂಲಗಳಲ್ಲಿ ಪರಿಶೀಲಿಸಿ.",
    kumbhTitle: "ಕುಂಭಮೇಳ ಗೈಡ್", kumbhDescription: "ನಾಶಿಕ್ ಕುಂಭ 2027, ಉಜ್ಜಯಿನಿ ಸಿಂಹಸ್ಥ 2028, ಪ್ರಯಾಗರಾಜ್ ಮತ್ತು ಹರಿದ್ವಾರ್ ಕುಂಭಕ್ಕೆ ಉಪಯುಕ್ತ ಪ್ರಯಾಣ ಮಾಹಿತಿ.",
    charTitle: "ಚಾರ ಧಾಮ ಯಾತ್ರೆ ಗೈಡ್", charDescription: "ಯಮುನೋತ್ರಿ, ಗಂಗೋತ್ರಿ, ಕೇದಾರನಾಥ್ ಮತ್ತು ಬದ್ರಿನಾಥ್‌ಗಾಗಿ ನೋಂದಣಿ, ಮಾರ್ಗ, ಆರೋಗ್ಯ, ವಸತಿ ಮತ್ತು ಹಿರಿಯರ ಯೋಜನೆ.",
    jyotiTitle: "12 ಜ್ಯೋತಿರ್ಲಿಂಗ ದರ್ಶನ ಗೈಡ್", jyotiDescription: "ಭಾರತದ 12 ಜ್ಯೋತಿರ್ಲಿಂಗಗಳನ್ನು ಪ್ರದೇಶವಾರು, ಕುಟುಂಬ ಮತ್ತು ಹಿರಿಯರಿಗೆ ಅನುಕೂಲವಾಗುವಂತೆ ಯೋಜಿಸಿ.",
    currentFocus: "ಪ್ರಸ್ತುತ ಗಮನ", nextFocus: "ಮುಂದಿನ ಮುಖ್ಯ ಗಮನ", services: "ಸೇವೆಗಳು", history: "ಇತಿಹಾಸ", stay: "ವಸತಿ", reach: "ಹೇಗೆ ತಲುಪುವುದು", faqs: "ಪ್ರಶ್ನೆಗಳು", packages: "ಪ್ಯಾಕೇಜುಗಳು",
  },
};

export function localizedPilgrimageTitle(locale: LocaleCode, path: string) {
  const c = copy[locale];
  if (path.startsWith("char-dham-yatra")) return c.charTitle;
  if (path.startsWith("12-jyotirlinga")) return c.jyotiTitle;
  if (path.startsWith("kumbh-mela")) return c.kumbhTitle;
  return c.allGuides;
}

export function LocalizedPilgrimagePage({ locale, segments }: { locale: LocaleCode; segments: string[] }) {
  const path = segments.join("/");
  if (segments[0] === "kumbh-mela") return <LocalizedKumbhPage locale={locale} segments={segments.slice(1)} />;
  if (segments[0] === "char-dham-yatra") return <LocalizedPillarPage locale={locale} pillar="char-dham" slug={segments[1]} />;
  if (segments[0] === "12-jyotirlinga") return <LocalizedPillarPage locale={locale} pillar="jyotirlinga" slug={segments[1]} />;
  return <LocalizedDirectoryPage locale={locale} path={path} />;
}

function LocalizedKumbhPage({ locale, segments }: { locale: LocaleCode; segments: string[] }) {
  const c = copy[locale];
  const slug = segments[0];
  const section = segments[1];
  const guide = slug ? getKumbhGuide(slug) : undefined;
  if (!guide && slug && slug !== "kumbh-calendar") return <LocalizedDirectoryPage locale={locale} path={`kumbh-mela/${segments.join("/")}`} />;
  if (!guide) {
    return <Shell locale={locale} eyebrow={c.currentFocus} title={c.kumbhTitle} subtitle={c.kumbhDescription} basePath="/kumbh-mela">
      <Grid>{kumbhGuides.map((item) => <GuideCard key={item.slug} href={`/kumbh-mela/${item.slug}`} locale={locale} badge={item.status === "current_focus" ? c.currentFocus : c.nextFocus} title={item.title} text={item.heroSubtitle} />)}</Grid>
    </Shell>;
  }
  return <Shell locale={locale} eyebrow={guide.status === "current_focus" ? c.currentFocus : c.nextFocus} title={section ? `${guide.shortTitle}: ${sectionLabel(c, section)}` : guide.heroTitle} subtitle={guide.heroSubtitle} basePath={`/kumbh-mela/${guide.slug}`}>
    <Summary c={c} facts={[["City", guide.city], ["State", guide.state], ["River", guide.river], ["Temple", guide.associatedTemple], ["Year", guide.eventYear]]} />
    <SectionCards locale={locale} c={c} base={`/kumbh-mela/${guide.slug}`} sections={["history", "places", "how-to-reach", "stay", "services", "packages", "faqs"]} />
    <Grid>{guide.keyPlaces.slice(0, 6).map((place) => <Info key={place.name} title={place.name} text={place.importance} />)}</Grid>
  </Shell>;
}

function LocalizedPillarPage({ locale, pillar, slug }: { locale: LocaleCode; pillar: "char-dham" | "jyotirlinga"; slug?: string }) {
  const c = copy[locale];
  const isChar = pillar === "char-dham";
  const title = isChar ? c.charTitle : c.jyotiTitle;
  const description = isChar ? c.charDescription : c.jyotiDescription;
  const base = isChar ? "/char-dham-yatra" : "/12-jyotirlinga";
  const site = slug ? (isChar ? getCharDhamGuide(slug) : getJyotirlingaGuide(slug)) : undefined;
  const sectionSlugs = isChar
    ? ["history", "registration", "route-map", "how-to-reach", "stay", "services", "senior-citizen-guide", "packages", "faqs"]
    : ["history", "complete-itinerary", "how-to-reach", "services", "senior-citizen-guide", "packages", "faqs"];
  if (!slug) {
    const sites = isChar ? charDhamGuides : jyotirlingaGuides;
    return <Shell locale={locale} eyebrow={c.allGuides} title={title} subtitle={description} basePath={base}>
      <SectionCards locale={locale} c={c} base={base} sections={sectionSlugs} />
      <Grid>{sites.map((item) => <GuideCard key={item.slug} locale={locale} href={`${base}/${item.slug}`} badge={isChar ? c.charTitle : c.jyotiTitle} title={item.templeName} text={item.shortDescription} />)}</Grid>
    </Shell>;
  }
  if (!site) {
    return <Shell locale={locale} eyebrow={c.sections} title={`${title}: ${sectionLabel(c, slug)}`} subtitle={description} basePath={`${base}/${slug}`}>
      <SectionCards locale={locale} c={c} base={base} sections={sectionSlugs} />
      <Grid>
        <Info title={c.verify} text={description} />
        <Info title={c.familySenior} text={isChar ? "Kedarnath and Yamunotri need slower planning, health checks and buffer days." : "Plan regional circuits and avoid peak festival crowd if travelling with elders."} />
      </Grid>
    </Shell>;
  }
  const facts = isChar
    ? [["Temple", site.templeName], ["State", site.state], ["Base", "baseTown" in site ? site.baseTown : ""], ["Airport", site.nearestAirport], ["Rail", site.nearestRailwayStation]]
    : [["Temple", site.templeName], ["City", "city" in site ? site.city : ""], ["State", site.state], ["Airport", site.nearestAirport], ["Rail", site.nearestRailwayStation]];
  return <Shell locale={locale} eyebrow={isChar ? c.charTitle : c.jyotiTitle} title={site.templeName} subtitle={site.shortDescription} basePath={`${base}/${site.slug}`}>
    <Summary c={c} facts={facts} />
    <Grid>{site.spiritualImportance.map((item) => <Info key={item} title={c.importantPlaces} text={item} />)}</Grid>
    <Grid>{site.usefulPlaces.slice(0, 6).map((place) => <Info key={place.name} title={place.name} text={place.importance} />)}</Grid>
  </Shell>;
}

function LocalizedDirectoryPage({ locale, path }: { locale: LocaleCode; path: string }) {
  const c = copy[locale];
  return <Shell locale={locale} eyebrow={c.allGuides} title={localizedPilgrimageTitle(locale, path)} subtitle={c.verify} basePath={`/${path}`}>
    <Grid>
      <GuideCard locale={locale} href="/kumbh-mela" badge={c.currentFocus} title={c.kumbhTitle} text={c.kumbhDescription} />
      <GuideCard locale={locale} href="/char-dham-yatra" badge={c.allGuides} title={c.charTitle} text={c.charDescription} />
      <GuideCard locale={locale} href="/12-jyotirlinga" badge={c.allGuides} title={c.jyotiTitle} text={c.jyotiDescription} />
    </Grid>
  </Shell>;
}

function Shell({ locale, eyebrow, title, subtitle, basePath, children }: { locale: LocaleCode; eyebrow: string; title: string; subtitle: string; basePath: string; children: ReactNode }) {
  const c = copy[locale];
  return <main>
    <section className="brand-gradient temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28">
      <div className="mx-auto max-w-7xl">
        <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold"><Languages className="h-4 w-4" />{c.languageLabel} · {eyebrow}</p>
        <h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{title}</h1>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{subtitle}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Button asChild size="lg"><Link href={localizedHref("/travel-tools", locale)}>{c.planTravel}<ArrowRight className="h-4 w-4" /></Link></Button>
          <Button asChild variant="outline" size="lg"><Link href={localizedHref(`${basePath}/packages`, locale)}>{c.packageQuote}</Link></Button>
        </div>
      </div>
    </section>
    <section className="bg-amber-50 px-4 py-5 text-sm leading-7 text-amber-950 sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl gap-3"><ShieldCheck className="mt-1 h-5 w-5 shrink-0 text-amber-700" />{c.verify}</div></section>
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl space-y-10">{children}</div></section>
  </main>;
}

function Summary({ c, facts }: { c: LocalCopy; facts: string[][] }) {
  return <div><h2 className="font-serif text-4xl font-semibold">{c.quickFacts}</h2><div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{facts.filter(([, value]) => value).map(([label, value]) => <Card key={label} className="border-gold/35 bg-white"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{label}</p><p className="mt-2 font-serif text-2xl">{value}</p></CardContent></Card>)}</div></div>;
}

function SectionCards({ locale, c, base, sections }: { locale: LocaleCode; c: LocalCopy; base: string; sections: string[] }) {
  return <div><h2 className="font-serif text-4xl font-semibold">{c.sections}</h2><div className="mt-6 grid gap-4 md:grid-cols-3">{sections.map((section) => <GuideCard key={section} href={`${base}/${section}`} locale={locale} badge={c.sections} title={sectionLabel(c, section)} text={c.verify} compact />)}</div></div>;
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{children}</div>;
}

function GuideCard({ locale, href, badge, title, text, compact = false }: { locale?: LocaleCode; href: string; badge: string; title: string; text: string; compact?: boolean }) {
  const target = locale ? localizedHref(href, locale) : href;
  return <Link href={target} className="group"><Card className="h-full border-gold/35 bg-white transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{badge}</p><h3 className={`mt-3 font-serif ${compact ? "text-xl" : "text-2xl"}`}>{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p><span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-maroon">Open<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>;
}

function Info({ title, text }: { title: string; text: string }) {
  return <Card className="h-full border-gold/35 bg-white"><CardContent><h3 className="font-serif text-2xl">{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>;
}

function sectionLabel(c: LocalCopy, section: string) {
  const labels: Record<string, string> = {
    history: c.history,
    places: c.importantPlaces,
    "how-to-reach": c.reach,
    stay: c.stay,
    services: c.services,
    packages: c.packages,
    faqs: c.faqs,
    registration: "Registration",
    "route-map": "Route Map",
    "complete-itinerary": "Complete Itinerary",
    "senior-citizen-guide": c.familySenior,
  };
  return labels[section] || section.replaceAll("-", " ");
}
