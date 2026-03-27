/**
 * TypeScript types matching backend Pydantic schemas.
 */

export type EventCategory =
  | "academic"
  | "social"
  | "career"
  | "arts"
  | "sports"
  | "other";

export interface EventRead {
  id: number;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string | null;
  location: string | null;
  source_url: string | null;
  source_name: string | null;
  category: EventCategory;
  tags: Record<string, unknown> | null;
  image_url: string | null;
  dedup_key: string;
  created_at: string;
  updated_at: string;
}

export interface EventList {
  items: EventRead[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface EventFilters {
  category?: EventCategory;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
  page_size?: number;
}
