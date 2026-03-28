import { format, parseISO, isSameDay } from "date-fns";

/**
 * Format event date: "Fri, Mar 28 · 7:00 PM" or "Fri, Mar 28 · 7:00 – 9:00 PM"
 */
export function formatEventDate(start: string, end?: string | null): string {
  const startDate = parseISO(start);
  const datePart = format(startDate, "EEE, MMM d");
  const startTime = format(startDate, "h:mm a");

  if (end) {
    const endDate = parseISO(end);
    if (isSameDay(startDate, endDate)) {
      const endTime = format(endDate, "h:mm a");
      return `${datePart} · ${startTime} – ${endTime}`;
    }
    const endFull = format(endDate, "EEE, MMM d · h:mm a");
    return `${datePart} · ${startTime} – ${endFull}`;
  }

  return `${datePart} · ${startTime}`;
}

/**
 * Format full event date: "Friday, March 28, 2026 at 7:00 PM"
 */
export function formatEventDateFull(start: string, end?: string | null): string {
  const startDate = parseISO(start);
  const full = format(startDate, "EEEE, MMMM d, yyyy 'at' h:mm a");

  if (end) {
    const endDate = parseISO(end);
    if (isSameDay(startDate, endDate)) {
      return `${full} – ${format(endDate, "h:mm a")}`;
    }
    return `${full} – ${format(endDate, "EEEE, MMMM d, yyyy 'at' h:mm a")}`;
  }

  return full;
}

/**
 * Returns Tailwind classes for category badges.
 */
export function categoryColor(category: string): string {
  const colors: Record<string, string> = {
    academic: "bg-blue-100 text-blue-800",
    social: "bg-emerald-100 text-emerald-800",
    career: "bg-orange-100 text-orange-800",
    arts: "bg-purple-100 text-purple-800",
    sports: "bg-red-100 text-red-800",
    other: "bg-gray-100 text-gray-700",
  };
  return colors[category] || colors.other;
}

/**
 * Capitalize category for display.
 */
export function categoryLabel(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}
