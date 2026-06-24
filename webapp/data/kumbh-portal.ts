import type { LocaleCode } from "@/lib/locale";

export type PortalLocale = LocaleCode | "en";

type PortalCopy = {
  brand: string;
  tagline: string;
  nav: string[];
  heroEyebrow: string;
  heroTitle: string;
  heroDescription: string;
  primaryCta: string;
  secondaryCta: string;
  focusNotice: string;
  upcomingEyebrow: string;
  upcomingTitle: string;
  upcomingDescription: string;
  whyTitle: string;
  whyDescription: string;
  latestTitle: string;
  alertsTitle: string;
  alertsDescription: string;
  alertButton: string;
  readGuide: string;
  schedulePending: string;
  fourCities: { city: string; river: string; text: string }[];
};

export const portalCopy: Record<PortalLocale, PortalCopy> = {
  en: {
    brand: "IndianKumbh", tagline: "One trusted guide for all Kumbh Melas in India",
    nav: ["Home", "Ujjain 2028", "Kumbh Calendar", "Mahakal", "Stay", "Plan Trip", "Guides"],
    heroEyebrow: "Primary guide · Ujjain Simhastha 2028", heroTitle: "Plan Ujjain Simhastha Kumbh 2028 with confidence", heroDescription: "A national Kumbh portal beginning with the deepest practical guide to Ujjain: Mahakal darshan, stays, routes, food, nearby trips and family itineraries.",
    primaryCta: "Plan Ujjain Trip", secondaryCta: "Explore Ujjain 2028",
    focusNotice: "Currently focused on Ujjain Simhastha 2028. Broader guides for Nashik, Prayagraj and Haridwar are being built.",
    upcomingEyebrow: "The national Kumbh roadmap", upcomingTitle: "Upcoming and evergreen Kumbh guides", upcomingDescription: "Follow one trusted structure across all four sacred Kumbh cities while official schedules are confirmed.",
    whyTitle: "Four sacred cities, one trusted planning standard", whyDescription: "Each Kumbh has its own river, travel pattern, sacred geography and crowd challenges. IndianKumbh brings them into one clear planning experience.",
    latestTitle: "Latest practical guides", alertsTitle: "Get Kumbh date and crowd alerts", alertsDescription: "Join the launch list for official-date reminders, new city guides and important planning updates.", alertButton: "Join alert list",
    readGuide: "Open guide", schedulePending: "Official schedule awaited",
    fourCities: [
      { city: "Ujjain", river: "Shipra", text: "Simhastha, Mahakal Jyotirlinga and the sacred old city." },
      { city: "Nashik–Trimbakeshwar", river: "Godavari", text: "A twin-city pilgrimage with Trimbakeshwar Jyotirlinga." },
      { city: "Prayagraj", river: "Sangam", text: "The confluence of Ganga, Yamuna and the sacred Saraswati tradition." },
      { city: "Haridwar", river: "Ganga", text: "Har Ki Pauri, Ganga aarti and Himalayan gateway travel." },
    ],
  },
  hi: {
    brand: "IndianKumbh", tagline: "भारत के सभी कुंभ मेलों की एक विश्वसनीय गाइड",
    nav: ["होम", "उज्जैन 2028", "कुंभ कैलेंडर", "महाकाल", "कहाँ ठहरें", "यात्रा बनाएँ", "गाइड"],
    heroEyebrow: "मुख्य गाइड · उज्जैन सिंहस्थ 2028", heroTitle: "उज्जैन सिंहस्थ कुंभ 2028 की भरोसेमंद योजना बनाएँ", heroDescription: "राष्ट्रीय कुंभ पोर्टल की शुरुआत उज्जैन की सबसे उपयोगी गाइड से—महाकाल दर्शन, ठहरना, मार्ग, भोजन और पारिवारिक कार्यक्रम।",
    primaryCta: "उज्जैन यात्रा बनाएँ", secondaryCta: "उज्जैन 2028 देखें",
    focusNotice: "अभी मुख्य ध्यान उज्जैन सिंहस्थ 2028 पर है। नाशिक, प्रयागराज और हरिद्वार की विस्तृत गाइड तैयार की जा रही हैं।",
    upcomingEyebrow: "राष्ट्रीय कुंभ मार्गदर्शिका", upcomingTitle: "आगामी और स्थायी कुंभ गाइड", upcomingDescription: "चारों पवित्र कुंभ शहरों के लिए एक जैसी स्पष्ट यात्रा योजना।",
    whyTitle: "चार पवित्र शहर, एक भरोसेमंद योजना", whyDescription: "हर कुंभ की नदी, यात्रा, धर्मस्थल और भीड़ अलग है। IndianKumbh इन्हें एक सरल अनुभव में जोड़ता है।",
    latestTitle: "नई उपयोगी गाइड", alertsTitle: "कुंभ तिथि और भीड़ अलर्ट पाएँ", alertsDescription: "आधिकारिक तिथि, नई शहर गाइड और महत्वपूर्ण यात्रा अपडेट के लिए सूची में जुड़ें।", alertButton: "अलर्ट सूची में जुड़ें",
    readGuide: "गाइड खोलें", schedulePending: "आधिकारिक कार्यक्रम की प्रतीक्षा",
    fourCities: [
      { city: "उज्जैन", river: "शिप्रा", text: "सिंहस्थ, महाकाल ज्योतिर्लिंग और पवित्र पुराना शहर।" },
      { city: "नाशिक–त्र्यंबकेश्वर", river: "गोदावरी", text: "त्र्यंबकेश्वर ज्योतिर्लिंग के साथ दो-शहर तीर्थयात्रा।" },
      { city: "प्रयागराज", river: "संगम", text: "गंगा, यमुना और पवित्र सरस्वती परंपरा का संगम।" },
      { city: "हरिद्वार", river: "गंगा", text: "हर की पौड़ी, गंगा आरती और हिमालय का प्रवेशद्वार।" },
    ],
  },
  bn: {
    brand: "IndianKumbh", tagline: "ভারতের সব কুম্ভমেলার একটি বিশ্বস্ত গাইড",
    nav: ["হোম", "উজ্জয়িনী ২০২৮", "কুম্ভ ক্যালেন্ডার", "মহাকাল", "থাকা", "ভ্রমণ পরিকল্পনা", "গাইড"],
    heroEyebrow: "প্রধান গাইড · উজ্জয়িনী সিংহস্থ ২০২৮", heroTitle: "উজ্জয়িনী সিংহস্থ কুম্ভ ২০২৮ আত্মবিশ্বাসের সঙ্গে পরিকল্পনা করুন", heroDescription: "জাতীয় কুম্ভ পোর্টালের শুরু উজ্জয়িনীর গভীর ব্যবহারিক গাইড দিয়ে—মহাকাল দর্শন, থাকা, পথ, খাবার ও পরিবার।",
    primaryCta: "উজ্জয়িনী ভ্রমণ সাজান", secondaryCta: "উজ্জয়িনী ২০২৮ দেখুন", focusNotice: "এখন মূল গুরুত্ব উজ্জয়িনী সিংহস্থ ২০২৮। নাশিক, প্রয়াগরাজ ও হরিদ্বারের বিস্তৃত গাইড তৈরি হচ্ছে।",
    upcomingEyebrow: "জাতীয় কুম্ভ রোডম্যাপ", upcomingTitle: "আসন্ন ও চিরস্থায়ী কুম্ভ গাইড", upcomingDescription: "চার পবিত্র কুম্ভ শহরের জন্য এক বিশ্বস্ত পরিকল্পনা কাঠামো।",
    whyTitle: "চার পবিত্র শহর, একটি বিশ্বস্ত মান", whyDescription: "প্রতিটি কুম্ভের নদী, যাত্রা ও ভিড় আলাদা। IndianKumbh সবকিছুকে একটি স্পষ্ট অভিজ্ঞতায় আনে।",
    latestTitle: "সর্বশেষ ব্যবহারিক গাইড", alertsTitle: "কুম্ভ তারিখ ও ভিড়ের সতর্কতা পান", alertsDescription: "সরকারি তারিখ, নতুন শহর গাইড ও গুরুত্বপূর্ণ আপডেটের তালিকায় যোগ দিন।", alertButton: "সতর্কতা তালিকায় যোগ দিন", readGuide: "গাইড খুলুন", schedulePending: "সরকারি সূচির অপেক্ষা",
    fourCities: [{ city: "উজ্জয়িনী", river: "শিপ্রা", text: "সিংহস্থ, মহাকাল জ্যোতির্লিঙ্গ ও পবিত্র পুরনো শহর।" }, { city: "নাশিক–ত্র্যম্বকেশ্বর", river: "গোদাবরী", text: "ত্র্যম্বকেশ্বর জ্যোতির্লিঙ্গসহ দুই-শহরের তীর্থযাত্রা।" }, { city: "প্রয়াগরাজ", river: "সঙ্গম", text: "গঙ্গা, যমুনা ও সরস্বতী ঐতিহ্যের সঙ্গম।" }, { city: "হরিদ্বার", river: "গঙ্গা", text: "হর কি পৌড়ি, গঙ্গা আরতি ও হিমালয়ের প্রবেশদ্বার।" }],
  },
  mr: {
    brand: "IndianKumbh", tagline: "भारतातील सर्व कुंभमेळ्यांसाठी एक विश्वासार्ह मार्गदर्शक",
    nav: ["मुख्यपृष्ठ", "उज्जैन २०२८", "कुंभ दिनदर्शिका", "महाकाल", "निवास", "प्रवास योजना", "मार्गदर्शक"],
    heroEyebrow: "मुख्य मार्गदर्शक · उज्जैन सिंहस्थ २०२८", heroTitle: "उज्जैन सिंहस्थ कुंभ २०२८ आत्मविश्वासाने नियोजित करा", heroDescription: "राष्ट्रीय कुंभ पोर्टलची सुरुवात उज्जैनच्या सखोल मार्गदर्शकाने—महाकाल दर्शन, निवास, मार्ग, खाद्य आणि कुटुंब दिनक्रम।",
    primaryCta: "उज्जैन प्रवास ठरवा", secondaryCta: "उज्जैन २०२८ पहा", focusNotice: "सध्या मुख्य लक्ष उज्जैन सिंहस्थ २०२८ वर आहे. नाशिक, प्रयागराज आणि हरिद्वार मार्गदर्शक तयार होत आहेत।",
    upcomingEyebrow: "राष्ट्रीय कुंभ आराखडा", upcomingTitle: "आगामी आणि सदाहरित कुंभ मार्गदर्शक", upcomingDescription: "चारही पवित्र कुंभ शहरांसाठी एक स्पष्ट नियोजन अनुभव।",
    whyTitle: "चार पवित्र शहरे, एक विश्वासार्ह मानक", whyDescription: "प्रत्येक कुंभाची नदी, प्रवास आणि गर्दी वेगळी आहे. IndianKumbh त्यांना एका स्पष्ट अनुभवात जोडते।",
    latestTitle: "नवीन उपयुक्त मार्गदर्शक", alertsTitle: "कुंभ तारीख आणि गर्दी सूचना मिळवा", alertsDescription: "अधिकृत तारखा, नवीन शहर मार्गदर्शक आणि महत्त्वाच्या अपडेटसाठी यादीत सामील व्हा।", alertButton: "सूचना यादीत सामील व्हा", readGuide: "मार्गदर्शक उघडा", schedulePending: "अधिकृत कार्यक्रमाची प्रतीक्षा",
    fourCities: [{ city: "उज्जैन", river: "शिप्रा", text: "सिंहस्थ, महाकाल ज्योतिर्लिंग आणि पवित्र जुने शहर।" }, { city: "नाशिक–त्र्यंबकेश्वर", river: "गोदावरी", text: "त्र्यंबकेश्वर ज्योतिर्लिंगासह दोन शहरांची तीर्थयात्रा।" }, { city: "प्रयागराज", river: "संगम", text: "गंगा, यमुना आणि सरस्वती परंपरेचा संगम।" }, { city: "हरिद्वार", river: "गंगा", text: "हर की पौडी, गंगा आरती आणि हिमालय प्रवेशद्वार।" }],
  },
  te: {
    brand: "IndianKumbh", tagline: "భారతదేశంలోని అన్ని కుంభమేళాలకు ఒక నమ్మకమైన గైడ్",
    nav: ["హోమ్", "ఉజ్జయిని 2028", "కుంభ క్యాలెండర్", "మహాకాళ్", "వసతి", "యాత్ర ప్రణాళిక", "గైడ్లు"],
    heroEyebrow: "ప్రధాన గైడ్ · ఉజ్జయిని సింహస్థ 2028", heroTitle: "ఉజ్జయిని సింహస్థ కుంభమేళా 2028ను నమ్మకంగా ప్లాన్ చేయండి", heroDescription: "జాతీయ కుంభ పోర్టల్ ఉజ్జయిని లోతైన గైడ్‌తో ప్రారంభమవుతుంది—మహాకాళ్ దర్శనం, వసతి, మార్గాలు, ఆహారం మరియు కుటుంబ ప్రణాళిక।",
    primaryCta: "ఉజ్జయిని యాత్ర ప్లాన్ చేయండి", secondaryCta: "ఉజ్జయిని 2028 చూడండి", focusNotice: "ప్రస్తుతం ఉజ్జయిని సింహస్థ 2028పై ప్రధాన దృష్టి. నాసిక్, ప్రయాగ్‌రాజ్, హరిద్వార్ గైడ్లు నిర్మాణంలో ఉన్నాయి।",
    upcomingEyebrow: "జాతీయ కుంభ మార్గపటం", upcomingTitle: "రాబోయే మరియు శాశ్వత కుంభ గైడ్లు", upcomingDescription: "నాలుగు పవిత్ర కుంభ నగరాలకు ఒక నమ్మకమైన ప్రణాళిక విధానం।",
    whyTitle: "నాలుగు పవిత్ర నగరాలు, ఒక నమ్మకమైన ప్రమాణం", whyDescription: "ప్రతి కుంభానికి నది, యాత్ర, జనసందోహం వేరు. IndianKumbh వాటిని స్పష్టంగా కలుపుతుంది।",
    latestTitle: "తాజా ఉపయోగకర గైడ్లు", alertsTitle: "కుంభ తేదీ మరియు జనసందోహ హెచ్చరికలు", alertsDescription: "అధికారిక తేదీలు, కొత్త నగర గైడ్లు మరియు ముఖ్యమైన నవీకరణల కోసం చేరండి।", alertButton: "హెచ్చరిక జాబితాలో చేరండి", readGuide: "గైడ్ తెరవండి", schedulePending: "అధికారిక షెడ్యూల్ కోసం వేచి ఉంది",
    fourCities: [{ city: "ఉజ్జయిని", river: "శిప్రా", text: "సింహస్థ, మహాకాళ్ జ్యోతిర్లింగం మరియు పవిత్ర పాత నగరం।" }, { city: "నాసిక్–త్ర్యంబకేశ్వర్", river: "గోదావరి", text: "త్ర్యంబకేశ్వర్ జ్యోతిర్లింగంతో రెండు నగరాల యాత్ర।" }, { city: "ప్రయాగ్‌రాజ్", river: "సంగమం", text: "గంగా, యమునా, సరస్వతి సంప్రదాయ సంగమం।" }, { city: "హరిద్వార్", river: "గంగా", text: "హర్ కీ పౌరీ, గంగా ఆరతి మరియు హిమాలయ ద్వారం।" }],
  },
  ta: {
    brand: "IndianKumbh", tagline: "இந்தியாவின் அனைத்து கும்பமேளாக்களுக்கும் ஒரு நம்பகமான வழிகாட்டி",
    nav: ["முகப்பு", "உஜ்ஜைன் 2028", "கும்ப காலண்டர்", "மகாகால்", "தங்குமிடம்", "பயணத் திட்டம்", "வழிகாட்டிகள்"],
    heroEyebrow: "முதன்மை வழிகாட்டி · உஜ்ஜைன் சிம்ஹஸ்தா 2028", heroTitle: "உஜ்ஜைன் சிம்ஹஸ்தா கும்பமேளா 2028 பயணத்தை நம்பிக்கையுடன் திட்டமிடுங்கள்", heroDescription: "தேசிய கும்ப போர்டல் உஜ்ஜைனின் ஆழமான நடைமுறை வழிகாட்டியுடன் தொடங்குகிறது—மகாகால் தரிசனம், தங்குமிடம், வழிகள், உணவு மற்றும் குடும்பத் திட்டம்।",
    primaryCta: "உஜ்ஜைன் பயணம் திட்டமிடு", secondaryCta: "உஜ்ஜைன் 2028 பாருங்கள்", focusNotice: "தற்போது உஜ்ஜைன் சிம்ஹஸ்தா 2028 மீது முதன்மை கவனம். நாசிக், பிரயாக்ராஜ், ஹரித்வார் வழிகாட்டிகள் உருவாக்கப்படுகின்றன।",
    upcomingEyebrow: "தேசிய கும்ப திட்டம்", upcomingTitle: "வரவிருக்கும் மற்றும் நிலையான கும்ப வழிகாட்டிகள்", upcomingDescription: "நான்கு புனித கும்ப நகரங்களுக்கும் ஒரே நம்பகமான திட்டமிடல் அனுபவம்।",
    whyTitle: "நான்கு புனித நகரங்கள், ஒரு நம்பகமான தரநிலை", whyDescription: "ஒவ்வொரு கும்பத்தின் நதி, பயணம், கூட்டம் வேறுபடும். IndianKumbh அவற்றை தெளிவாக இணைக்கிறது।",
    latestTitle: "சமீபத்திய நடைமுறை வழிகாட்டிகள்", alertsTitle: "கும்ப தேதி மற்றும் கூட்ட எச்சரிக்கைகள்", alertsDescription: "அதிகாரப்பூர்வ தேதிகள், புதிய நகர வழிகாட்டிகள் மற்றும் முக்கிய புதுப்பிப்புகளுக்கு சேருங்கள்।", alertButton: "எச்சரிக்கை பட்டியலில் சேருங்கள்", readGuide: "வழிகாட்டி திறக்கவும்", schedulePending: "அதிகாரப்பூர்வ அட்டவணை நிலுவையில்",
    fourCities: [{ city: "உஜ்ஜைன்", river: "ஷிப்ரா", text: "சிம்ஹஸ்தா, மகாகால் ஜோதிர்லிங்கம் மற்றும் புனித பழைய நகரம்।" }, { city: "நாசிக்–திரியம்பகேஸ்வர்", river: "கோதாவரி", text: "திரியம்பகேஸ்வர் ஜோதிர்லிங்கத்துடன் இரு நகர யாத்திரை।" }, { city: "பிரயாக்ராஜ்", river: "சங்கமம்", text: "கங்கை, யமுனை மற்றும் சரஸ்வதி மரபின் சங்கமம்।" }, { city: "ஹரித்வார்", river: "கங்கை", text: "ஹர் கி பௌரி, கங்கை ஆரத்தி மற்றும் இமயமலை நுழைவாயில்।" }],
  },
  kn: {
    brand: "IndianKumbh", tagline: "ಭಾರತದ ಎಲ್ಲಾ ಕುಂಭಮೇಳಗಳಿಗೆ ಒಂದು ನಂಬಿಕಸ್ಥ ಮಾರ್ಗದರ್ಶಿ",
    nav: ["ಮುಖಪುಟ", "ಉಜ್ಜಯಿನಿ 2028", "ಕುಂಭ ಕ್ಯಾಲೆಂಡರ್", "ಮಹಾಕಾಳ", "ವಸತಿ", "ಪ್ರಯಾಣ ಯೋಜನೆ", "ಮಾರ್ಗದರ್ಶಿಗಳು"],
    heroEyebrow: "ಮುಖ್ಯ ಮಾರ್ಗದರ್ಶಿ · ಉಜ್ಜಯಿನಿ ಸಿಂಹಸ್ಥ 2028", heroTitle: "ಉಜ್ಜಯಿನಿ ಸಿಂಹಸ್ಥ ಕುಂಭಮೇಳ 2028 ಪ್ರಯಾಣವನ್ನು ವಿಶ್ವಾಸದಿಂದ ಯೋಜಿಸಿ", heroDescription: "ರಾಷ್ಟ್ರೀಯ ಕುಂಭ ಪೋರ್ಟಲ್ ಉಜ್ಜಯಿನಿಯ ಆಳವಾದ ಮಾರ್ಗದರ್ಶಿಯಿಂದ ಆರಂಭವಾಗುತ್ತದೆ—ಮಹಾಕಾಳ ದರ್ಶನ, ವಸತಿ, ಮಾರ್ಗ, ಆಹಾರ ಮತ್ತು ಕುಟುಂಬ ಯೋಜನೆ।",
    primaryCta: "ಉಜ್ಜಯಿನಿ ಪ್ರಯಾಣ ಯೋಜಿಸಿ", secondaryCta: "ಉಜ್ಜಯಿನಿ 2028 ನೋಡಿ", focusNotice: "ಪ್ರಸ್ತುತ ಉಜ್ಜಯಿನಿ ಸಿಂಹಸ್ಥ 2028 ಮುಖ್ಯ ಗಮನ. ನಾಸಿಕ್, ಪ್ರಯಾಗರಾಜ್ ಮತ್ತು ಹರಿದ್ವಾರ ಮಾರ್ಗದರ್ಶಿಗಳು ನಿರ್ಮಾಣದಲ್ಲಿವೆ।",
    upcomingEyebrow: "ರಾಷ್ಟ್ರೀಯ ಕುಂಭ ಮಾರ್ಗನಕ್ಷೆ", upcomingTitle: "ಮುಂಬರುವ ಮತ್ತು ಶಾಶ್ವತ ಕುಂಭ ಮಾರ್ಗದರ್ಶಿಗಳು", upcomingDescription: "ನಾಲ್ಕು ಪವಿತ್ರ ಕುಂಭ ನಗರಗಳಿಗೆ ಒಂದೇ ನಂಬಿಕಸ್ಥ ಯೋಜನಾ ಅನುಭವ।",
    whyTitle: "ನಾಲ್ಕು ಪವಿತ್ರ ನಗರಗಳು, ಒಂದು ನಂಬಿಕಸ್ಥ ಮಾನದಂಡ", whyDescription: "ಪ್ರತಿ ಕುಂಭದ ನದಿ, ಪ್ರಯಾಣ ಮತ್ತು ಜನಸಂದಣಿ ವಿಭಿನ್ನ. IndianKumbh ಅವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಜೋಡಿಸುತ್ತದೆ।",
    latestTitle: "ಇತ್ತೀಚಿನ ಉಪಯುಕ್ತ ಮಾರ್ಗದರ್ಶಿಗಳು", alertsTitle: "ಕುಂಭ ದಿನಾಂಕ ಮತ್ತು ಜನಸಂದಣಿ ಎಚ್ಚರಿಕೆ", alertsDescription: "ಅಧಿಕೃತ ದಿನಾಂಕಗಳು, ಹೊಸ ನಗರ ಮಾರ್ಗದರ್ಶಿಗಳು ಮತ್ತು ಮುಖ್ಯ ನವೀಕರಣಗಳಿಗೆ ಸೇರಿ।", alertButton: "ಎಚ್ಚರಿಕೆ ಪಟ್ಟಿಗೆ ಸೇರಿ", readGuide: "ಮಾರ್ಗದರ್ಶಿ ತೆರೆಯಿರಿ", schedulePending: "ಅಧಿಕೃತ ವೇಳಾಪಟ್ಟಿ ಬಾಕಿ",
    fourCities: [{ city: "ಉಜ್ಜಯಿನಿ", river: "ಶಿಪ್ರಾ", text: "ಸಿಂಹಸ್ಥ, ಮಹಾಕಾಳ ಜ್ಯೋತಿರ್ಲಿಂಗ ಮತ್ತು ಪವಿತ್ರ ಹಳೆಯ ನಗರ।" }, { city: "ನಾಸಿಕ್–ತ್ರ್ಯಂಬಕೇಶ್ವರ", river: "ಗೋದಾವರಿ", text: "ತ್ರ್ಯಂಬಕೇಶ್ವರ ಜ್ಯೋತಿರ್ಲಿಂಗದೊಂದಿಗೆ ಎರಡು ನಗರ ಯಾತ್ರೆ।" }, { city: "ಪ್ರಯಾಗರಾಜ್", river: "ಸಂಗಮ", text: "ಗಂಗಾ, ಯಮುನಾ ಮತ್ತು ಸರಸ್ವತಿ ಪರಂಪರೆಯ ಸಂಗಮ।" }, { city: "ಹರಿದ್ವಾರ", river: "ಗಂಗಾ", text: "ಹರ್ ಕಿ ಪೌರಿ, ಗಂಗಾ ಆರತಿ ಮತ್ತು ಹಿಮಾಲಯದ ದ್ವಾರ।" }],
  },
};

export const latestGuides = [
  { title: "Mahakal darshan planning without uncertain timings", href: "/mahakal-temple-guide", category: "Ujjain 2028" },
  { title: "Ujjain vs Indore vs Bhopal: choose your base", href: "/stay-guide", category: "Stay guide" },
  { title: "A calm family itinerary for Ujjain and Omkareshwar", href: "/itineraries", category: "Itinerary" },
];
