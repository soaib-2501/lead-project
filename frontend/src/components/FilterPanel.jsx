import { useState } from "react";

const PRESETS = {
  none: { label: "No preset", apply: () => true },
  webDevLeads: {
    label: "No Website + Good Rating (Web-Dev Leads)",
    apply: (r) => !r.website && r.rating !== null && r.rating >= 4,
  },
  marketingLeads: {
    label: "Has Website + Low Reviews (Marketing Leads)",
    apply: (r) => !!r.website && r.reviews < 100,
  },
  noPhone: {
    label: "No Phone (Contact Gap)",
    apply: (r) => !r.phone,
  },
};

const RATING_OPTIONS = [
  { value: "any", label: "Rating: Any" },
  { value: "gt-3", label: "Rating > 3" },
  { value: "gt-3.5", label: "Rating > 3.5" },
  { value: "gt-4", label: "Rating > 4" },
  { value: "gt-4.5", label: "Rating > 4.5" },
  { value: "lt-3", label: "Rating < 3" },
  { value: "lt-3.5", label: "Rating < 3.5" },
  { value: "lt-4", label: "Rating < 4" },
];

const REVIEWS_OPTIONS = [
  { value: "any", label: "Reviews: Any" },
  { value: "gt-50", label: "Reviews > 50" },
  { value: "gt-100", label: "Reviews > 100" },
  { value: "gt-200", label: "Reviews > 200" },
  { value: "gt-500", label: "Reviews > 500" },
  { value: "lt-50", label: "Reviews < 50" },
  { value: "lt-100", label: "Reviews < 100" },
  { value: "lt-200", label: "Reviews < 200" },
];

function parseThreshold(val) {
  if (val === "any") return null;
  const [op, num] = val.split("-");
  return { op, num: Number(num) };
}

// Shared select style — highlighted (blue) when set to a non-default value
function selectClass(isActive) {
  return `border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
    isActive
      ? "border-blue-500 bg-blue-50 text-blue-700 font-medium"
      : "border-gray-300 bg-white text-gray-700"
  }`;
}

export default function FilterPanel({ results, onFilteredChange }) {
  const [websiteFilter, setWebsiteFilter] = useState("any");
  const [phoneFilter, setPhoneFilter] = useState("any");
  const [ratingFilter, setRatingFilter] = useState("any");
  const [reviewsFilter, setReviewsFilter] = useState("any");
  const [preset, setPreset] = useState("none");

  const applyFilters = () => {
    let filtered = results;

    if (preset !== "none") {
      filtered = filtered.filter(PRESETS[preset].apply);
    }

    if (websiteFilter === "has") filtered = filtered.filter((r) => !!r.website);
    if (websiteFilter === "none") filtered = filtered.filter((r) => !r.website);

    if (phoneFilter === "has") filtered = filtered.filter((r) => !!r.phone);
    if (phoneFilter === "none") filtered = filtered.filter((r) => !r.phone);

    const rating = parseThreshold(ratingFilter);
    if (rating) {
      filtered = filtered.filter((r) => {
        if (r.rating === null) return false;
        return rating.op === "gt" ? r.rating > rating.num : r.rating < rating.num;
      });
    }

    const reviews = parseThreshold(reviewsFilter);
    if (reviews) {
      filtered = filtered.filter((r) =>
        reviews.op === "gt" ? r.reviews > reviews.num : r.reviews < reviews.num
      );
    }

    onFilteredChange(filtered);
  };

  const activeCount = [
    preset !== "none",
    websiteFilter !== "any",
    phoneFilter !== "any",
    ratingFilter !== "any",
    reviewsFilter !== "any",
  ].filter(Boolean).length;

  if (results.length === 0) return null;

  return (
    <div className="bg-gray-50 rounded-xl p-4 mb-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          className={selectClass(preset !== "none")}
        >
          <option value="none">Opportunity preset...</option>
          {Object.entries(PRESETS)
            .filter(([k]) => k !== "none")
            .map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
        </select>

        <select
          value={websiteFilter}
          onChange={(e) => setWebsiteFilter(e.target.value)}
          className={selectClass(websiteFilter !== "any")}
        >
          <option value="any">Website: Any</option>
          <option value="has">Has Website</option>
          <option value="none">No Website</option>
        </select>

        <select
          value={phoneFilter}
          onChange={(e) => setPhoneFilter(e.target.value)}
          className={selectClass(phoneFilter !== "any")}
        >
          <option value="any">Phone: Any</option>
          <option value="has">Has Phone</option>
          <option value="none">No Phone</option>
        </select>

        <select
          value={ratingFilter}
          onChange={(e) => setRatingFilter(e.target.value)}
          className={selectClass(ratingFilter !== "any")}
        >
          {RATING_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          value={reviewsFilter}
          onChange={(e) => setReviewsFilter(e.target.value)}
          className={selectClass(reviewsFilter !== "any")}
        >
          {REVIEWS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <button
          onClick={applyFilters}
          className="bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg px-4 py-2 text-sm transition-colors"
        >
          Apply Filters
        </button>

        {activeCount > 0 && (
          <span className="text-xs font-medium text-blue-600 bg-blue-100 rounded-full px-2.5 py-1">
            {activeCount} filter{activeCount > 1 ? "s" : ""} active
          </span>
        )}
      </div>
    </div>
  );
}