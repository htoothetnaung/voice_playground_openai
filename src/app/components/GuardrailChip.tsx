import React, { useState } from "react";
import {
  CheckCircledIcon,
  ClockIcon,
  CrossCircledIcon,
} from "@radix-ui/react-icons";

import { GuardrailResultType } from "../types";

function formatCategory(category: string): string {
  return category
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function GuardrailChip({
  guardrailResult,
}: {
  guardrailResult: GuardrailResultType;
}) {
  const [expanded, setExpanded] = useState(false);

  const state =
    guardrailResult.status === "IN_PROGRESS"
      ? "PENDING"
      : guardrailResult.category === "NONE"
      ? "PASS"
      : "FAIL";

  let IconComponent;
  let label: string;
  let wrapperClass: string;
  let pillClass: string;

  switch (state) {
    case "PENDING":
      IconComponent = ClockIcon;
      label = "Pending review";
      wrapperClass = "border-slate-200 bg-white text-slate-600";
      pillClass = "bg-slate-100 text-slate-600";
      break;
    case "PASS":
      IconComponent = CheckCircledIcon;
      label = "Passed";
      wrapperClass = "border-emerald-200 bg-emerald-50 text-emerald-800";
      pillClass = "bg-emerald-100 text-emerald-700";
      break;
    case "FAIL":
      IconComponent = CrossCircledIcon;
      label = "Flagged";
      wrapperClass = "border-rose-200 bg-rose-50 text-rose-800";
      pillClass = "bg-rose-100 text-rose-700";
      break;
    default:
      IconComponent = ClockIcon;
      label = "Pending review";
      wrapperClass = "border-slate-200 bg-white text-slate-600";
      pillClass = "bg-slate-100 text-slate-600";
  }

  return (
    <div className="text-xs">
      <div
        onClick={() => {
          if (state !== "PENDING") {
            setExpanded(!expanded);
          }
        }}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 ${wrapperClass} ${
          state !== "PENDING" ? "cursor-pointer" : ""
        }`}
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide">
          Guardrail
        </span>
        <span className={`flex items-center gap-1 rounded-full px-2 py-1 ${pillClass}`}>
          <IconComponent /> {label}
        </span>
      </div>

      {state !== "PENDING" &&
        guardrailResult.category &&
        guardrailResult.rationale && (
          <div
            className={`overflow-hidden transition-all duration-300 ${
              expanded ? "max-h-[1000px] opacity-100" : "max-h-0 opacity-0"
            }`}
          >
            <div className="pt-3 text-xs text-slate-700">
              <strong>
                Moderation Category: {formatCategory(guardrailResult.category)}
              </strong>
              <div className="mt-1">{guardrailResult.rationale}</div>
              {guardrailResult.testText && (
                <blockquote className="mt-2 border-l-2 border-slate-300 pl-2 text-slate-500">
                  {guardrailResult.testText}
                </blockquote>
              )}
            </div>
          </div>
        )}
    </div>
  );
}
