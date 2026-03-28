import type {
  EventList,
  EventRead,
  EventFilters,
  OrganizationList,
  OrganizationFilters,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Fetch a paginated, filtered list of events.
 */
export async function getEvents(filters: EventFilters = {}): Promise<EventList> {
  const params = new URLSearchParams();

  if (filters.category) params.set("category", filters.category);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.search) params.set("search", filters.search);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));

  const query = params.toString();
  const url = `${API_URL}/events${query ? `?${query}` : ""}`;

  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch a single event by ID.
 */
export async function getEvent(id: number): Promise<EventRead> {
  const res = await fetch(`${API_URL}/events/${id}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch a paginated, filtered list of organizations.
 */
export async function getOrganizations(
  filters: OrganizationFilters = {}
): Promise<OrganizationList> {
  const params = new URLSearchParams();

  if (filters.category) params.set("category", filters.category);
  if (filters.search) params.set("search", filters.search);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));

  const query = params.toString();
  const url = `${API_URL}/organizations${query ? `?${query}` : ""}`;

  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
