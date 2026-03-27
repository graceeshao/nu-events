/**
 * Card component displaying a single event's details.
 */

import { format } from "date-fns";
import type { EventRead } from "@/lib/types";

interface EventCardProps {
  event: EventRead;
}

const CATEGORY_BADGE: Record<string, string> = {
  academic: "badge-academic",
  social: "badge-social",
  career: "badge-career",
  arts: "badge-arts",
  sports: "badge-sports",
  other: "badge-other",
};

export function EventCard({ event }: EventCardProps) {
  const startDate = new Date(event.start_time);
  const formattedDate = format(startDate, "EEE, MMM d · h:mm a");
  const badgeClass = CATEGORY_BADGE[event.category] || "badge-other";

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-shadow overflow-hidden">
      {event.image_url && (
        <img
          src={event.image_url}
          alt={event.title}
          className="w-full h-40 object-cover"
        />
      )}
      <div className="p-5">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-semibold text-lg text-gray-900 leading-tight">
            {event.title}
          </h3>
          <span
            className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${badgeClass}`}
          >
            {event.category}
          </span>
        </div>

        <p className="text-sm text-nu-purple-500 font-medium mb-1">
          📅 {formattedDate}
        </p>

        {event.location && (
          <p className="text-sm text-gray-500 mb-2">📍 {event.location}</p>
        )}

        {event.description && (
          <p className="text-sm text-gray-600 line-clamp-2 mb-3">
            {event.description}
          </p>
        )}

        <div className="flex items-center justify-between text-xs text-gray-400">
          {event.source_name && <span>via {event.source_name}</span>}
          {event.source_url && (
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-nu-purple hover:underline"
            >
              View source →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
