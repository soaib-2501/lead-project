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

// value format: "any" | "gt-<num>" | "lt-<num>"
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

// parses "gt-3.5" -> { op: "gt", num: 3.5 }, "any" -> null
function parseThreshold(val) {
  if (val === "any") return null;
  const [op, num] = val.split("-");
  return { op, num: Number(num) };
}

export default function FilterPanel({ results, onFilteredChange }) {
  const [websiteFilter, setWebsiteFilter] = useState("any"); // any | has | none
  const [phoneFilter, setPhoneFilter] = useState("any");     // any | has | none
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

  if (results.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.6rem",
        padding: "1rem",
        marginBottom: "1rem",
        background: "#f5f5f5",
        borderRadius: "8px",
      }}
    >
      <select value={preset} onChange={(e) => setPreset(e.target.value)} style={{ padding: "0.4rem" }}>
        <option value="none">Opportunity preset...</option>
        {Object.entries(PRESETS)
          .filter(([k]) => k !== "none")
          .map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
      </select>

      <select value={websiteFilter} onChange={(e) => setWebsiteFilter(e.target.value)} style={{ padding: "0.4rem" }}>
        <option value="any">Website: Any</option>
        <option value="has">Has Website</option>
        <option value="none">No Website</option>
      </select>

      <select value={phoneFilter} onChange={(e) => setPhoneFilter(e.target.value)} style={{ padding: "0.4rem" }}>
        <option value="any">Phone: Any</option>
        <option value="has">Has Phone</option>
        <option value="none">No Phone</option>
      </select>

      <select value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)} style={{ padding: "0.4rem" }}>
        {RATING_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <select value={reviewsFilter} onChange={(e) => setReviewsFilter(e.target.value)} style={{ padding: "0.4rem" }}>
        {REVIEWS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <button  onClick={applyFilters} style={{ padding: "0.4rem 1.2rem" }}>
        Apply Filters
      </button>
    </div>
  );
}