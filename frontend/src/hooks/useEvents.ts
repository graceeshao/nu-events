/**
 * Custom hook for fetching and filtering events with loading state.
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import { getEvents } from "@/lib/api";
import type { EventRead, EventFilters } from "@/lib/types";

interface UseEventsResult {
  events: EventRead[];
  total: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useEvents(filters: EventFilters = {}): UseEventsResult {
  const [events, setEvents] = useState<EventRead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filterKey = JSON.stringify(filters);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getEvents(filters);
      setEvents(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  return { events, total, loading, error, refetch: fetchEvents };
}
