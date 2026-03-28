import { notFound } from "next/navigation";
import Link from "next/link";
import { getEvent } from "@/lib/api";
import { formatEventDateFull, categoryColor, categoryLabel } from "@/lib/utils";

interface Props {
  params: { id: string };
}

export default async function EventDetailPage({ params }: Props) {
  const id = Number(params.id);
  if (isNaN(id)) notFound();

  let event;
  try {
    event = await getEvent(id);
  } catch {
    notFound();
  }

  return (
    <div className="max-w-3xl mx-auto">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-nu-purple transition mb-6"
      >
        ← Back to events
      </Link>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900 leading-tight">
              {event.title}
            </h1>
            {event.has_free_food && (
              <span className="shrink-0 text-sm font-medium px-3 py-1 rounded-full bg-amber-100 text-amber-700">
                🍕 Free Food!
              </span>
            )}
          </div>
          <span
            className={`shrink-0 text-xs font-medium px-3 py-1 rounded-full ${categoryColor(
              event.category
            )}`}
          >
            {categoryLabel(event.category)}
          </span>
        </div>

        <div className="mt-5 space-y-3 text-sm text-gray-600">
          <p className="flex items-start gap-2">
            <span>📅</span>
            <span>{formatEventDateFull(event.start_time, event.end_time)}</span>
          </p>
          {event.location && (
            <p className="flex items-start gap-2">
              <span>📍</span>
              <span>{event.location}</span>
            </p>
          )}
          {event.source_name && (
            <p className="flex items-start gap-2">
              <span>🔗</span>
              {event.source_url ? (
                <a
                  href={event.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-nu-purple hover:underline"
                >
                  {event.source_name}
                </a>
              ) : (
                <span>{event.source_name}</span>
              )}
            </p>
          )}
        </div>

        {event.description && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">
              About this event
            </h2>
            <p className="text-sm text-gray-600 whitespace-pre-line leading-relaxed">
              {event.description}
            </p>
          </div>
        )}

        {event.rsvp_url && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <a
              href={event.rsvp_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-nu-purple text-white font-medium hover:bg-nu-purple-700 transition"
            >
              RSVP / Register →
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
