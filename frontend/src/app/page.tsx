"use client";

import { useEvents } from "@/hooks/useEvents";
import FilterBar from "@/components/FilterBar";
import EventList from "@/components/EventList";
import Pagination from "@/components/Pagination";

export default function HomePage() {
  const {
    events,
    pages,
    page,
    loading,
    error,
    search,
    category,
    dateRange,
    showSchool,
    showFitness,
    setSearch,
    setCategory,
    setDateRange,
    setShowSchool,
    setShowFitness,
    setPage,
  } = useEvents();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Campus Events
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Discover what&apos;s happening at Northwestern
        </p>
      </div>

      <FilterBar
        search={search}
        onSearchChange={setSearch}
        category={category}
        onCategoryChange={setCategory}
        dateRange={dateRange}
        onDateRangeChange={setDateRange}
        showSchool={showSchool}
        onShowSchoolChange={setShowSchool}
        showFitness={showFitness}
        onShowFitnessChange={setShowFitness}
      />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          Failed to load events: {error}
        </div>
      )}

      <EventList events={events} loading={loading} />

      <Pagination page={page} pages={pages} onPageChange={setPage} />
    </div>
  );
}
