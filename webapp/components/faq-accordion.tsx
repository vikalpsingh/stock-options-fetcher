"use client";

import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";

export function FAQAccordion({ items }: { items: { question: string; answer: string }[] }) {
  return (
    <Accordion.Root type="single" collapsible className="space-y-3">
      {items.map((item, index) => (
        <Accordion.Item key={item.question} value={`item-${index}`} className="overflow-hidden rounded-2xl border border-stone-200 bg-white">
          <Accordion.Header>
            <Accordion.Trigger className="group flex w-full items-center justify-between gap-4 p-5 text-left font-serif text-lg font-semibold text-ink sm:p-6 sm:text-xl">
              {item.question}<ChevronDown className="h-5 w-5 shrink-0 text-saffron transition group-data-[state=open]:rotate-180" />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content className="overflow-hidden data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
            <p className="px-5 pb-5 leading-7 text-stone-600 sm:px-6 sm:pb-6">{item.answer}</p>
          </Accordion.Content>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
