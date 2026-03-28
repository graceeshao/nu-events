import Link from "next/link";
import type { EventRead } from "@/lib/types";
import { formatEventDate, categoryColor, categoryLabel } from "@/lib/utils";

export default function EventCard({ event }: { event: EventRead }) {
  return (
    <Link
      href={`/events/${event.id}`}
      className="block bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-nu-purple-200 transition-all duration-200 p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="font-semibold text-gray-900 leading-snug line-clamp-2">
            {event.title}
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

      {event.description && (
        <p className="mt-2 text-sm text-gray-600 line-clamp-2">
          {event.description.length > 100
            ? event.description.slice(0, 100) + "…"
            : event.description}
        </p>
      )}

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
