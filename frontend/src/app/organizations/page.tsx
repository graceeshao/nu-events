"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getOrganizations } from "@/lib/api";
import type { OrganizationRead } from "@/lib/types";
import Pagination from "@/components/Pagination";

const CATEGORIES = ["All", "RSO", "TGS", "FSL", "Media", "Sports Club", "Other"];

function OrgCard({ org }: { org: OrganizationRead }) {
  const tags: string[] = Array.isArray(org.tags) ? org.tags : [];

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold text-gray-900 leading-snug">
          {org.name}
        </h3>
        <span className="shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full bg-nu-purple-50 text-nu-purple">
          {org.category}
        </span>
      </div>

      {tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {tags.slice(0, 5).map((tag) => (
            <span
              key={tag}
              className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full"
            >
              {tag}
            </span>
          ))}
          {tags.length > 5 && (
            <span className="text-xs text-gray-400">+{tags.length - 5}</span>
          )}
        </div>
      )}

      <div className="mt-3 flex gap-3 text-xs">
        {org.instagram_handle && (
          <a
            href={`https://instagram.com/${org.instagram_handle}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-nu-purple hover:underline"
          >
            📸 Instagram
          </a>
        )}
        {org.website && (
          <a
            href={org.website}
            target="_blank"
            rel="noopener noreferrer"
            className="text-nu-purple hover:underline"
          >
            🌐 Website
          </a>
        )}
        {org.email && (
          <a
            href={`mailto:${org.email}`}
            className="text-nu-purple hover:underline"
          >
            ✉️ Email
          </a>
        )}
      </div>
    </div>
  );
}

export default function OrganizationsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [orgs, setOrgs] = useState<OrganizationRead[]>([]);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearch = useCallback((value: string) => {
    setSearch(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    getOrganizations({
      search: debouncedSearch || undefined,
      category: category,
      page,
      page_size: 12,
    })
      .then((data) => {
        if (!cancelled) {
          setOrgs(data.items);
          setPages(data.pages);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, category, page]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Organizations</h1>
        <p className="text-sm text-gray-500 mt-1">
          Browse Northwestern student organizations
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg">
          🔍
        </span>
        <input
          type="text"
          placeholder="Search organizations..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-gray-300 bg-white text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-nu-purple/30 focus:border-nu-purple transition"
        />
      </div>

      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mb-1">
        {CATEGORIES.map((cat) => {
          const isActive =
            cat === "All" ? category === undefined : category === cat;
          return (
            <button
              key={cat}
              onClick={() => {
                setCategory(cat === "All" ? undefined : cat);
                setPage(1);
              }}
              className={`shrink-0 px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                isActive
                  ? "bg-nu-purple text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {cat}
            </button>
          );
        })}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse"
            >
              <div className="h-5 bg-gray-200 rounded w-3/4" />
              <div className="mt-3 h-4 bg-gray-100 rounded w-1/3" />
            </div>
          ))}
        </div>
      ) : orgs.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-4xl mb-3">🏫</p>
          <p className="text-lg font-medium text-gray-700">
            No organizations found
          </p>
          <p className="text-sm text-gray-500 mt-1">
            Try adjusting your search or filters.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {orgs.map((org) => (
            <OrgCard key={org.id} org={org} />
          ))}
        </div>
      )}

      <Pagination page={page} pages={pages} onPageChange={setPage} />
    </div>
  );
}
