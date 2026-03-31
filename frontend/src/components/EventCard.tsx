import Link from "next/link";
import type { EventRead } from "@/lib/types";
import { formatEventDate, categoryColor, categoryLabel } from "@/lib/utils";

function cleanTitle(title: string): string {
  let t = title;

  // Remove trailing date/time after a separator: ": Wednesday, 4/1 from 7:00 - in Tech"
  const days = "(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)";
  t = t.replace(new RegExp(`[:\\|]\\s*${days}[,.]?\\s*\\d{1,2}\\/\\d{1,2}.*$`, "i"), "").trim();
  // "| Friday 4/11 at 8pm"
  t = t.replace(new RegExp(`[:\\|]\\s*${days}\\s+\\d{1,2}\\/\\d{1,2}\\b.*$`, "i"), "").trim();
  // Trailing bare date after separator: "| 4/1 from 7:00..."
  t = t.replace(/[:\|]\s*\d{1,2}\/\d{1,2}\b.*$/i, "").trim();

  // Remove trailing "from 7:00" or "at 8pm" style suffixes
  t = t.replace(/\s+(from|at)\s+\d{1,2}(:\d{2})?\s*(am|pm)?\s*[-–—]?\s*$/i, "").trim();

  // Clean up leftover trailing separators
  t = t.replace(/[\s\-–—|:,]+$/, "").trim();
  t = t.replace(/\s{2,}/g, " ").trim();
  return t || title;
}

function getSummary(event: EventRead): string | null {
  const desc = event.description?.trim();

  // Has a real description — use it
  if (desc && desc.length > 30 && !["tba", "tbd", "title: tba", "."].includes(desc.toLowerCase())) {
    // Strip HTML entities and clean up
    const clean = desc.replace(/&#\d+;/g, " ").replace(/\s+/g, " ").trim();
    return clean.length > 120 ? clean.slice(0, 120) + "…" : clean;
  }

  // Build a contextual summary from available fields
  const parts: string[] = [];

  // Use source info
  if (event.source_name?.startsWith("Instagram:@")) {
    const handle = event.source_name.replace("Instagram:", "");
    parts.push(`Event by ${handle}`);
  } else if (event.source_name === "PlanIt Purple") {
    parts.push("Northwestern campus event");
  } else if (event.source_name) {
    parts.push(`Shared by ${event.source_name}`);
  }

  // Add location context
  if (event.location) {
    parts.push(`at ${event.location.split(",")[0]}`);
  }

  // Add category context
  if (event.category && event.category !== "other") {
    const catMap: Record<string, string> = {
      social: "Social event",
      academic: "Academic event",
      career: "Career event",
      arts: "Arts & culture",
      sports: "Sports & recreation",
    };
    if (parts.length === 0) {
      parts.push(catMap[event.category] || "");
    }
  }

  // Add food tag
  if (event.has_free_food && parts.length > 0) {
    parts.push("— free food!");
  }

  return parts.length > 0 ? parts.join(" ") : null;
}

export default function EventCard({ event }: { event: EventRead }) {
  return (
    <Link
      href={`/events/${event.id}`}
      className="block bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-nu-purple-200 transition-all duration-200 p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="font-semibold text-gray-900 leading-snug line-clamp-2">
            {cleanTitle(event.title)}
          </h3>
          {event.has_free_food && (
            <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
              🍕 Free Food
            </span>
          )}
        </div>
        <span
          className={`shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full ${categoryColor(
            event.category
          )}`}
        >
          {categoryLabel(event.category)}
        </span>
      </div>

      {(() => {
        const summary = getSummary(event);
        return summary ? (
          <p className="mt-2 text-sm text-gray-600 line-clamp-2">
            {summary}
          </p>
        ) : null;
      })()}

      <div className="mt-3 space-y-1.5 text-sm text-gray-500">
        <p>📅 {formatEventDate(event.start_time, event.end_time)}</p>
        {event.location && (
          <p className="truncate">📍 {event.location}</p>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        {event.source_name && (
          <p className="text-xs text-gray-400">
            via {event.source_name}
          </p>
        )}
        {event.rsvp_url && (
          <a
            href={event.rsvp_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-xs font-medium text-nu-purple hover:underline px-3 py-1 rounded-full border border-nu-purple-200 hover:bg-nu-purple-50 transition"
          >
            RSVP →
          </a>
        )}
      </div>
    </Link>
  );
}
