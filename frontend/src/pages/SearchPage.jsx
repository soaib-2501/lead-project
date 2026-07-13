import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import FilterPanel from "../components/FilterPanel";
import { useSearchContext } from "../context/SearchContext";
import { Search, MapPin, LayoutGrid, Sparkles, Star, Phone, Mail, Globe, Clock, Download } from "lucide-react";

// Converts an array of business objects into a CSV file and triggers a
// browser download. Kept local to this page since it's the only place
// export is triggered from — no need for a separate service file for one
// small pure function.
function exportToCsv(businesses) {
  if (!businesses || businesses.length === 0) return;

  const columns = [
    { key: "name", label: "Name" },
    { key: "category", label: "Category" },
    { key: "address", label: "Address" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
    { key: "website", label: "Website" },
    { key: "rating", label: "Rating" },
    { key: "reviews", label: "Reviews" },
    { key: "opening_hours", label: "Opening Hours" },
  ];

  // Escapes a single CSV field: wraps in quotes and doubles any internal
  // quotes, per standard CSV escaping. Anything with a comma, quote, or
  // newline needs quoting; simplest to just always quote every field.
  const escapeCell = (value) => {
    const str = value === null || value === undefined ? "" : String(value);
    return `"${str.replace(/"/g, '""')}"`;
  };

  const headerRow = columns.map((col) => escapeCell(col.label)).join(",");
  const dataRows = businesses.map((biz) =>
    columns.map((col) => escapeCell(biz[col.key])).join(",")
  );

  const csvContent = [headerRow, ...dataRows].join("\r\n");

  // Prefix with a UTF-8 BOM so Excel opens the file with correct encoding
  // instead of mangling non-ASCII characters in names/addresses.
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  link.download = `lead-search-results-${timestamp}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function SearchPage() {
  const navigate = useNavigate();

  const {
    form, setForm,
    results, setResults,
    filtered, setFiltered,
    loading, setLoading,
    error, setError,
  } = useSearchContext();

  useEffect(() => {
    setFiltered(results);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResults([]);

    try {
      const response = await api.post("/api/search", {
        ...form,
        max_results: Number(form.max_results),
      });
      setResults(response.data);
    } catch (err) {
      console.error("[SearchPage] Search failed:", err);
      setError("Search failed. Backend not reachable or scraping error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const formatOpeningHours = (raw) => {
    if (!raw) return null;
    return raw.split("|").map((line) => line.trim()).filter(Boolean);
  };

  const goToDetail = (biz) => {
    const slug = encodeURIComponent(biz.name.toLowerCase().replace(/\s+/g, "-"));
    navigate(`/business/${slug}`, { state: { business: biz } });
  };

  return (
    <div className="relative w-full min-h-screen overflow-hidden bg-gradient-to-br from-indigo-50 via-white to-rose-50">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-blob absolute -top-24 -left-24 h-72 w-72 rounded-full bg-indigo-300/30 blur-3xl" />
        <div
          className="animate-blob absolute top-1/3 -right-32 h-96 w-96 rounded-full bg-blue-300/30 blur-3xl"
          style={{ animationDelay: "2s" }}
        />
        <div
          className="animate-blob absolute bottom-0 left-1/4 h-80 w-80 rounded-full bg-rose-200/40 blur-3xl"
          style={{ animationDelay: "4s" }}
        />
      </div>

      <div className="relative px-4 py-10 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-5xl">
          <div className="animate-fade-up flex flex-col items-center text-center mb-10">
            <div className="flex items-center gap-3">
              <div className="animate-float animate-glow-pulse flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-blue-600 to-violet-600">
                <Sparkles className="h-7 w-7 text-white" strokeWidth={2} />
              </div>
              <h1 className="animate-gradient bg-gradient-to-r from-slate-900 via-indigo-700 to-slate-900 bg-clip-text text-4xl sm:text-5xl font-extrabold text-transparent tracking-tight">
                Lead Search
              </h1>
            </div>
            <p className="text-slate-500 text-sm sm:text-base mt-3">
              Find businesses across any city — fast, filtered, and ready to export.
            </p>
          </div>

          <form
            onSubmit={handleSearch}
            className="animate-fade-up bg-white/80 backdrop-blur-xl rounded-3xl shadow-2xl shadow-indigo-100 border border-white/60 p-5 sm:p-8 mb-8"
            style={{ animationDelay: "0.1s" }}
          >
            <div className="relative mb-6 group">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 transition-colors group-focus-within:text-indigo-500" />
              <input
                name="keyword"
                placeholder="Keyword (optional)"
                value={form.keyword}
                onChange={handleChange}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/80 pl-11 pr-4 py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent focus:bg-white transition-all"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50">
                    <MapPin className="h-4 w-4 text-indigo-600" />
                  </span>
                  <span className="text-sm font-semibold text-slate-800">Choose city</span>
                </div>
                <input
                  name="city"
                  placeholder="Noida, Delhi, Mumbai..."
                  value={form.city}
                  onChange={handleChange}
                  required
                  className="w-full rounded-xl border border-slate-200 px-4 py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-all"
                />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50">
                    <LayoutGrid className="h-4 w-4 text-indigo-600" />
                  </span>
                  <span className="text-sm font-semibold text-slate-800">Select category</span>
                </div>
                <input
                  name="category"
                  placeholder="Restaurants, Gyms, Clinics..."
                  value={form.category}
                  onChange={handleChange}
                  required
                  className="w-full rounded-xl border border-slate-200 px-4 py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-all"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px] gap-3 mb-7">
              <input
                name="area"
                placeholder="Area (optional, e.g. Sector 62)"
                value={form.area}
                onChange={handleChange}
                className="w-full rounded-xl border border-slate-200 px-4 py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-all"
              />
              <input
                type="number"
                name="max_results"
                placeholder="Max results"
                value={form.max_results}
                onChange={handleChange}
                min={1}
                max={100}
                className="w-full rounded-xl border border-slate-200 px-4 py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-all"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 via-blue-600 to-violet-600 hover:shadow-xl hover:shadow-indigo-300/50 hover:-translate-y-0.5 disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0 text-white font-semibold text-sm px-4 py-4 shadow-lg shadow-indigo-200 transition-all duration-200"
            >
              <Sparkles className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              {loading ? "Searching..." : "Start smart search"}
            </button>
          </form>

          {loading && (
            <p className="animate-fade-up text-slate-500 text-sm mb-4 text-center">
              Scraping in progress — this can take 1–3 minutes depending on result count. Please wait.
            </p>
          )}

          {error && (
            <p className="animate-fade-up text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-6 text-sm text-center">
              {error}
            </p>
          )}

          {!loading && results.length > 0 && (
            <div className="animate-fade-up">
              <FilterPanel results={results} onFilteredChange={setFiltered} />

              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <p className="text-slate-500 text-sm">
                  Showing <span className="font-semibold text-slate-700">{filtered.length}</span> of{" "}
                  <span className="font-semibold text-slate-700">{results.length}</span> results
                </p>

                <button
                  type="button"
                  onClick={() => exportToCsv(filtered)}
                  disabled={filtered.length === 0}
                  className="inline-flex items-center gap-2 rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-2.5 text-sm font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-600 hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  <Download className="h-4 w-4" /> Export CSV
                </button>
              </div>

              <div className="hidden md:block overflow-x-auto bg-white/90 backdrop-blur rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-100">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b border-slate-100 bg-slate-50/80 text-slate-500 uppercase text-xs tracking-wide">
                      <th className="p-4 font-semibold">Name</th>
                      <th className="p-4 font-semibold">Category</th>
                      <th className="p-4 font-semibold">Address</th>
                      <th className="p-4 font-semibold">Phone</th>
                      <th className="p-4 font-semibold">Email</th>
                      <th className="p-4 font-semibold">Website</th>
                      <th className="p-4 font-semibold text-center">Rating</th>
                      <th className="p-4 font-semibold text-center">Reviews</th>
                      <th className="p-4 font-semibold min-w-[220px]">Opening Hours</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((biz, idx) => {
                      const hoursList = formatOpeningHours(biz.opening_hours);
                      return (
                        <tr key={idx} className="border-b border-slate-50 align-top hover:bg-indigo-50/40 transition-colors">
                          <td className="p-4 font-semibold text-slate-900">
                            <button
                              type="button"
                              onClick={() => goToDetail(biz)}
                              className="text-left hover:text-indigo-600 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-400 rounded transition-colors"
                            >
                              {biz.name}
                            </button>
                          </td>
                          <td className="p-4 text-slate-600">{biz.category || "-"}</td>
                          <td className="p-4 text-slate-600 max-w-xs">{biz.address || "-"}</td>
                          <td className="p-4 text-slate-600 whitespace-nowrap">{biz.phone || "-"}</td>
                          <td className="p-4">
                            {biz.email ? (
                              <a
                                href={`mailto:${biz.email}`}
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-medium break-all"
                              >
                                <Mail className="h-3.5 w-3.5 shrink-0" /> {biz.email}
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                          <td className="p-4">
                            {biz.website ? (
                              <a
                                href={biz.website}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-medium"
                              >
                                <Globe className="h-3.5 w-3.5" /> Visit
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                          <td className="p-4 text-center whitespace-nowrap">
                            {biz.rating !== null && biz.rating !== undefined ? (
                              <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
                                <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" /> {biz.rating}
                              </span>
                            ) : (
                              <span className="text-slate-400">N/A</span>
                            )}
                          </td>
                          <td className="p-4 text-center text-slate-600">{biz.reviews}</td>
                          <td className="p-4 text-xs text-slate-500">
                            {hoursList ? (
                              <ul className="space-y-0.5">
                                {hoursList.map((line, i) => (
                                  <li key={i} className="flex items-start gap-1">
                                    <Clock className="h-3 w-3 mt-0.5 shrink-0 text-slate-400" />
                                    <span>{line}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              "N/A"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="md:hidden space-y-4">
                {filtered.map((biz, idx) => {
                  const hoursList = formatOpeningHours(biz.opening_hours);
                  return (
                    <div
                      key={idx}
                      onClick={() => goToDetail(biz)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && goToDetail(biz)}
                      className="bg-white/90 backdrop-blur rounded-2xl shadow-lg shadow-slate-200/50 border border-slate-100 p-4 cursor-pointer hover:shadow-xl hover:border-indigo-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    >
                      <p className="font-semibold text-slate-900 mb-1">{biz.name}</p>
                      <p className="text-sm text-slate-500 mb-2">{biz.category || "-"}</p>

                      <div className="space-y-1.5 mb-3">
                        <p className="text-sm text-slate-600 flex items-start gap-2">
                          <MapPin className="h-4 w-4 mt-0.5 shrink-0 text-slate-400" />
                          <span>{biz.address || "-"}</span>
                        </p>
                        <p className="text-sm text-slate-600 flex items-center gap-2">
                          <Phone className="h-4 w-4 shrink-0 text-slate-400" />
                          <span>{biz.phone || "-"}</span>
                        </p>
                        {biz.email && (
                          <p className="text-sm text-slate-600 flex items-center gap-2">
                            <Mail className="h-4 w-4 shrink-0 text-slate-400" />
                            <span className="break-all">{biz.email}</span>
                          </p>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-3 text-sm mb-2">
                        {biz.rating !== null && biz.rating !== undefined ? (
                          <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
                            <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" /> {biz.rating}
                          </span>
                        ) : (
                          <span className="text-slate-400">N/A</span>
                        )}
                        <span className="text-slate-500">{biz.reviews} reviews</span>
                        {biz.website && (
                          <a
                            href={biz.website}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 text-indigo-600 font-medium"
                          >
                            <Globe className="h-3.5 w-3.5" /> Visit
                          </a>
                        )}
                      </div>

                      {hoursList && (
                        <ul className="text-xs text-slate-500 space-y-0.5 border-t border-slate-100 pt-2 mt-2">
                          {hoursList.map((line, i) => (
                            <li key={i} className="flex items-start gap-1">
                              <Clock className="h-3 w-3 mt-0.5 shrink-0 text-slate-400" />
                              <span>{line}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </div>

              {filtered.length === 0 && (
                <p className="text-slate-400 mt-6 text-center">No results match these filters.</p>
              )}
            </div>
          )}

          {!loading && !error && results.length === 0 && (
            <p className="text-slate-400 text-center">No results yet — run a search above.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default SearchPage;