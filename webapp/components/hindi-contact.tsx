import { Mail, MessageCircle } from "lucide-react";
import type { LocaleCode } from "@/lib/locale";
import { uiCopy } from "@/data/locale-ui";

const labels: Record<LocaleCode, string[]> = {
  hi: ["नाम", "ईमेल", "यात्रा का महीना", "परिवार के सदस्य", "हम कैसे सहायता कर सकते हैं?", "पूछताछ भेजें"],
  bn: ["নাম", "ইমেল", "ভ্রমণের মাস", "পরিবারের সদস্য", "আমরা কীভাবে সাহায্য করতে পারি?", "জিজ্ঞাসা পাঠান"],
  mr: ["नाव", "ईमेल", "प्रवासाचा महिना", "कुटुंब सदस्य", "आम्ही कशी मदत करू?", "चौकशी पाठवा"],
  te: ["పేరు", "ఇమెయిల్", "ప్రయాణ నెల", "కుటుంబ సభ్యులు", "మేము ఎలా సహాయం చేయాలి?", "విచారణ పంపండి"],
  ta: ["பெயர்", "மின்னஞ்சல்", "பயண மாதம்", "குடும்ப உறுப்பினர்கள்", "எவ்வாறு உதவலாம்?", "விசாரணை அனுப்பவும்"],
  kn: ["ಹೆಸರು", "ಇಮೇಲ್", "ಪ್ರಯಾಣ ತಿಂಗಳು", "ಕುಟುಂಬ ಸದಸ್ಯರು", "ನಾವು ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?", "ವಿಚಾರಣೆ ಕಳುಹಿಸಿ"],
};

export function HindiContact({ locale }: { locale: LocaleCode }) {
  const copy = uiCopy[locale];
  const text = labels[locale];
  return <main className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-2">
    <div><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.footerTrust}</p><h1 className="mt-3 font-serif text-5xl font-semibold leading-tight text-ink sm:text-6xl">{copy.enquiry}</h1><p className="mt-5 max-w-lg text-lg leading-8 text-stone-600">{copy.plannerDescription}</p><div className="mt-9 space-y-4 text-sm font-semibold text-stone-700"><p className="flex items-center gap-3"><Mail className="text-saffron" />info@indiankumbh.com</p><p className="flex items-center gap-3"><Mail className="text-saffron" />support@indiankumbh.com</p><p className="flex items-center gap-3"><MessageCircle className="text-[#1f9d55]" />WhatsApp</p></div></div>
    <form className="rounded-[2rem] bg-white p-7 shadow-soft sm:p-9"><div className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-bold">{text[0]}<input className="form-control" /></label><label className="text-sm font-bold">{text[1]}<input type="email" className="form-control" /></label><label className="text-sm font-bold">{text[2]}<input type="month" className="form-control" /></label><label className="text-sm font-bold">{text[3]}<input type="number" min="1" className="form-control" /></label></div><label className="mt-5 block text-sm font-bold">{text[4]}<textarea rows={5} className="mt-2 w-full rounded-xl border border-stone-300 p-4 font-normal outline-none focus:border-saffron" /></label><button type="button" className="mt-6 w-full rounded-full bg-saffron px-6 py-4 text-sm font-bold text-white">{text[5]}</button></form>
  </div></main>;
}
