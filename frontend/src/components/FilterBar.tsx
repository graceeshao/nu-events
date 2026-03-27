/**
 * Filter bar with category dropdown, date range, and search input.
 */

"use client";

import type { EventCategory, EventFilters } from "@/lib/types";

interface FilterBarProps {
  filters: EventFilters;
  onChange: (filters: EventFilters) => void;
}

const CATEGORIES: { value: EventCategory | ""; label: string }[] = [
  { value: "", label: "All Categories" },
  { value: "academic", label: "🎓 Academic" },
  { value: "social", label: "🎉 Social" },
  { value: "career", label: "💼 Career" },
  { value: "arts", label: "🎨 Arts" },
  { value: "sports", label: "⚽ Sports" },
  { value: "other", label: "📌 Other" },
];

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const update = (partial: Partial<EventFilters>) => {
    onChange({ ...filters, ...partial, page: 1 });
  };

  return (
    <div className="flex flex-col sm:flex-row gap-3">
      {/* Search */}
      <div className="flex-1">
        <input
          type="text"
          placeholder="Search events..."
          value={filters.search || ""}
          onChange={(e) => update({ search: e.target.value || undefined })}
          className="w-full px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nu-purple-300 focus:border-nu-purple-400 text-sm"
        />
      </div>

      {/* Category */}
      <select
        value={filters.category || ""}
        onChange={(e) =>
          update({
            category: (e.target.value as EventCategory) || undefined,
          })
        }
        className="px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nu-purple-300 focus:border-nu-purple-400 text-sm bg-white"
      >
        {CATEGORIES.map((cat) => (
          <option key={cat.value} value={cat.value}>
            {cat.label}
          </option>
        ))}
      </select>

      {/* Date from */}
      <input
        type="date"
        value={filters.date_from?.split("T")[0] || ""}
        onChange={(e) =>
          update({
            date_from: e.target.value
              ? `${e.target.value}T00:00:00`
              : undefined,
          })
        }
        className="px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nu-purple-300 focus:border-nu-purple-400 text-sm"
        title="From date"
      />

      {/* Date to */}
      <input
        type="date"
        value={filters.date_to?.split("T")[0] || ""}
        onChange={(e) =>
          update({
            date_to: e.target.value
              ? `${e.target.value}T23:59:59`
              : undefined,
          })
        }
        className="px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nu-purple-300 focus:border-nu-purple-400 text-sm"
        title="To date"
      />
    </div>
  );
}
