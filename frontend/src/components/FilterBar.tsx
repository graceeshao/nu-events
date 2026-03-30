"use client";

import type { EventCategory } from "@/lib/types";
import { categoryLabel } from "@/lib/utils";

const CATEGORIES: (EventCategory | "all")[] = [
  "all",
  "academic",
  "social",
  "career",
  "arts",
  "sports",
  "other",
];

type DateRange = "all" | "today" | "week" | "month";

interface FilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  category: EventCategory | undefined;
  onCategoryChange: (value: EventCategory | undefined) => void;
  dateRange: DateRange;
  onDateRangeChange: (value: DateRange) => void;
  showFitness: boolean;
  onShowFitnessChange: (value: boolean) => void;
}

export default function FilterBar({
  search,
  onSearchChange,
  category,
  onCategoryChange,
  dateRange,
  onDateRangeChange,
  showFitness,
  onShowFitnessChange,
}: FilterBarProps) {
  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg">
          🔍
        </span>
        <input
          type="text"
          placeholder="Search events..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-gray-300 bg-white text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-nu-purple/30 focus:border-nu-purple transition"
        />
      </div>

      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mb-1 scrollbar-hide">
        {CATEGORIES.map((cat) => {
          const isActive =
            cat === "all" ? category === undefined : category === cat;
          return (
            <button
              key={cat}
              onClick={() =>
                onCategoryChange(cat === "all" ? undefined : (cat as EventCategory))
              }
              className={`shrink-0 px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                isActive
                  ? "bg-nu-purple text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {cat === "all" ? "All" : categoryLabel(cat)}
            </button>
          );
        })}
      </div>

      {/* Date range + Fitness toggle */}
      <div className="flex gap-2 items-center flex-wrap">
        {(
          [
            ["all", "All Dates"],
            ["today", "Today"],
            ["week", "This Week"],
            ["month", "This Month"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => onDateRangeChange(value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              dateRange === value
                ? "bg-nu-purple-50 text-nu-purple border border-nu-purple/20"
                : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            {label}
          </button>
        ))}

        <span className="mx-1 text-gray-300">|</span>

        <button
          onClick={() => onShowFitnessChange(!showFitness)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            showFitness
              ? "bg-nu-purple-50 text-nu-purple border border-nu-purple/20"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          🏋️ Fitness
        </button>
      </div>
    </div>
  );
}
