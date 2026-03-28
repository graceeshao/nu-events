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
        <h3 className="font-semibold text-gray-900 leading-snug line-clamp-2">
          {event.title}
        </h3>
        <span
          className={`shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full ${categoryColor(
            event.category
          )}`}
        >
          {categoryLabel(event.category)}
        </span>
      </div>

      <div className="mt-3 space-y-1.5 text-sm text-gray-500">
        <p>📅 {formatEventDate(event.start_time, event.end_time)}</p>
        {event.location && (
          <p className="truncate">📍 {event.location}</p>
        )}
      </div>

      {event.source_name && (
        <p className="mt-3 text-xs text-gray-400">
          via {event.source_name}
        </p>
      )}
    </Link>
  );
}
