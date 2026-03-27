"use client";

import { Header } from "@/components/Header";
import { FilterBar } from "@/components/FilterBar";
import { EventList } from "@/components/EventList";
import { useEvents } from "@/hooks/useEvents";
import type { EventFilters } from "@/lib/types";
import { useState } from "react";

export default function HomePage() {
  const [filters, setFilters] = useState<EventFilters>({});
  const { events, total, loading, error } = useEvents(filters);

  return (
    <>
      <Header />
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-8">
        <FilterBar filters={filters} onChange={setFilters} />
        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            Failed to load events. Is the backend running?
          </div>
        )}
        <EventList events={events} loading={loading} />
        {!loading && total > 0 && (
          <p className="mt-6 text-center text-sm text-gray-500">
            Showing {events.length} of {total} events
          </p>
        )}
      </main>
      <footer className="text-center py-6 text-sm text-gray-400 border-t">
        NU Events · Northwestern University · Built with 💜
      </footer>
    </>
  );
}
