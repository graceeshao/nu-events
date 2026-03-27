/**
 * Renders a grid of EventCards with loading and empty states.
 */

import { EventCard } from "./EventCard";
import type { EventRead } from "@/lib/types";

interface EventListProps {
  events: EventRead[];
  loading: boolean;
}

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse"
        >
          <div className="h-5 bg-gray-200 rounded w-3/4 mb-3" />
          <div className="h-4 bg-gray-100 rounded w-1/2 mb-2" />
          <div className="h-4 bg-gray-100 rounded w-1/3 mb-4" />
          <div className="h-3 bg-gray-50 rounded w-full mb-1" />
          <div className="h-3 bg-gray-50 rounded w-2/3" />
        </div>
      ))}
    </div>
  );
}

export function EventList({ events, loading }: EventListProps) {
  if (loading) {
    return <LoadingSkeleton />;
  }

  if (events.length === 0) {
    return (
      <div className="mt-12 text-center">
        <p className="text-5xl mb-4">🎓</p>
        <p className="text-lg text-gray-500">No events found</p>
        <p className="text-sm text-gray-400 mt-1">
          Try adjusting your filters or check back later.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
      {events.map((event) => (
        <EventCard key={event.id} event={event} />
      ))}
    </div>
  );
}
