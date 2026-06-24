"use client";

import { Printer } from "lucide-react";
import { Button } from "./ui/button";

export function WorkingPrintButton() {
  return <Button onClick={() => window.print()} variant="outline"><Printer className="h-4 w-4" />Print / save PDF</Button>;
}
