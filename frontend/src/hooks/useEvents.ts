"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getEvents } from "@/lib/api";
import type { EventCategory, EventList } from "@/lib/types";
import { startOfDay, endOfDay, startOfWeek, endOfWeek, startOfMonth, endOfMonth, format } from "date-fns";

type DateRange = "all" | "today" | "week" | "month";

function getDateBounds(range: DateRange): { from?: string; to?: string } {
  if (range === "all") return {};
  const now = new Date();
  const fmt = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm:ss");
  switch (range) {
    case "today":
      return { from: fmt(startOfDay(now)), to: fmt(endOfDay(now)) };
    case "week":
      return { from: fmt(startOfWeek(now)), to: fmt(endOfWeek(now)) };
    case "month":
      return { from: fmt(startOfMonth(now)), to: fmt(endOfMonth(now)) };
  }
}

export function useEvents() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<EventCategory | undefined>();
  const [dateRange, setDateRange] = useState<DateRange>("all");
  const [showSchool, setShowSchool] = useState(false);
  const [showFitness, setShowFitness] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EventList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce search
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }, []);

  const handleCategoryChange = useCallback((cat: EventCategory | undefined) => {
    setCategory(cat);
    setPage(1);
  }, []);

  const handleDateRangeChange = useCallback((range: DateRange) => {
    setDateRange(range);
    setPage(1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const dates = getDateBounds(dateRange);

    getEvents({
      search: debouncedSearch || undefined,
      category,
      date_from: dates.from,
      date_to: dates.to,
      include_school: showSchool || undefined,
      include_fitness: (showSchool && showFitness) || undefined,
      page,
      page_size: 12,
    })
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, category, dateRange, showSchool, showFitness, page]);

  return {
    events: data?.items ?? [],
    total: data?.total ?? 0,
    page: data?.page ?? page,
    pages: data?.pages ?? 1,
    loading,
    error,
    search,
    category,
    dateRange,
    showSchool,
    showFitness,
    setSearch: handleSearchChange,
    setCategory: handleCategoryChange,
    setDateRange: handleDateRangeChange,
    setShowSchool,
    setShowFitness,
    setPage,
  };
}
