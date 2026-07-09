import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import FilterPanel from "../components/FilterPanel";
import { useSearchContext } from "../context/SearchContext";
import { Search, MapPin, LayoutGrid, Sparkles, Star, Phone, Globe, Clock, Loader2 } from "lucide-react";

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

  const handleSearch = (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResults([]);

    // EventSource (Server-Sent Events) instead of a single api.post() call.
    // The backend now yields each business the moment it's scraped, instead
    // of waiting for the whole batch — so results appear in the table live,
    // one by one, instead of everything showing up at once after 1-3 minutes.
    //
    // EventSource only supports GET with no custom body, so search params
    // travel as a query string. We reuse the same base URL as the axios
    // `api` instance so this points at the same backend it's configured for.
    const params = new URLSearchParams({
      city: form.city,
      category: form.category,
      max_results: String(form.max_results),
    });
    if (form.area) params.set("area", form.area);
    if (form.keyword) params.set("keyword", form.keyword);

    const base = api.defaults.baseURL || "";
    const streamUrl = `${base}/api/search/stream?${params.toString()}`;

    const source = new EventSource(streamUrl);

    source.addEventListener("business", (event) => {
      const biz = JSON.parse(event.data);
      setResults((prev) => [...prev, biz]);
    });

    source.addEventListener("done", () => {
      setLoading(false);
      source.close();
    });

    // EventSource fires a plain "error" event both for our custom SSE
    // "error" message AND for real connection failures (backend down,
    // network drop). Custom messages always carry event.data; connection
    // failures don't — that's how we tell the two apart.
    source.addEventListener("error", (event) => {
      if (event.data) {
        try {
          const payload = JSON.parse(event.data);
          console.error("[SearchPage] Stream reported an error:", payload.message);
        } catch {
          // ignore parse failure, fall through to generic message below
        }
      } else {
        console.error("[SearchPage] EventSource connection error", event);
      }
      setError("Search failed. Backend not reachable or scraping error occurred.");
      setLoading(false);
      source.close();
    });
  };

  // Groups consecutive days that share the exact same hours into a single
  // "Mon-Fri: 7:30am - 11pm" line instead of listing all 7 days separately.
  const DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const DAY_ABBR = {
    Monday: "Mon", Tuesday: "Tue", Wednesday: "Wed", Thursday: "Thu",
    Friday: "Fri", Saturday: "Sat", Sunday: "Sun",
  };

  const formatOpeningHours = (raw) => {
    if (!raw) return null;
    const lines = raw.split("|").map((line) => line.trim()).filter(Boolean);
    if (lines.length === 0) return null;

    const parsed = lines.map((line) => {
      const day = DAY_ORDER.find((d) => line.startsWith(d));
      return day ? { day, time: line.slice(day.length).trim() } : { day: null, time: line };
    });

    if (parsed.every((p) => !p.day)) return lines;

    const byDay = {};
    parsed.forEach((p) => {
      if (p.day) byDay[p.day] = p.time;
    });
    const ordered = DAY_ORDER
      .map((day, index) => ({ day, index, time: byDay[day] }))
      .filter((d) => d.time !== undefined);

    if (ordered.length === 0) return lines;

    const groups = [];
    ordered.forEach(({ day, index, time }) => {
      const last = groups[groups.length - 1];
      if (last && last.time === time && index === last.endIndex + 1) {
        last.endDay = day;
        last.endIndex = index;
      } else {
        groups.push({ startDay: day, endDay: day, endIndex: index, time });
      }
    });

    return groups.map(({ startDay, endDay, time }) => {
      const label = startDay === endDay ? DAY_ABBR[startDay] : `${DAY_ABBR[startDay]}-${DAY_ABBR[endDay]}`;
      return `${label}: ${time}`;
    });
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

          {/* Shown only before the FIRST result has arrived */}
          {loading && results.length === 0 && (
            <p className="animate-fade-up text-slate-500 text-sm mb-4 text-center">
              Scraping in progress — results will appear below as they're found. Please wait.
            </p>
          )}

          {error && (
            <p className="animate-fade-up text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-6 text-sm text-center">
              {error}
            </p>
          )}

          {/* Results now render as soon as the first business arrives, even
              while `loading` is still true — that's the whole point of
              streaming. A separate "fetching more..." bar below the table
              (not this block) communicates that more may still be coming. */}
          {results.length > 0 && (
            <div className="animate-fade-up">
              <FilterPanel results={results} onFilteredChange={setFiltered} />

              <p className="text-slate-500 text-sm mb-4">
                Showing <span className="font-semibold text-slate-700">{filtered.length}</span> of{" "}
                <span className="font-semibold text-slate-700">{results.length}</span> results
                {loading && " (more coming...)"}
              </p>

              <div className="hidden md:block overflow-x-auto bg-white/90 backdrop-blur rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-100">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b border-slate-100 bg-slate-50/80 text-slate-500 uppercase text-xs tracking-wide">
                      <th className="p-4 font-semibold">Name</th>
                      <th className="p-4 font-semibold">Category</th>
                      <th className="p-4 font-semibold">Address</th>
                      <th className="p-4 font-semibold">Phone</th>
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
                        <tr key={biz.place_id || idx} className="border-b border-slate-50 align-top hover:bg-indigo-50/40 transition-colors animate-fade-up">
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

                {/* "More results loading" bar — lives inside the table card,
                    right under the last row, until the "done" SSE event closes it out. */}
                {loading && (
                  <div className="flex items-center justify-center gap-2 border-t border-slate-100 py-4 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                    Fetching more businesses — {results.length} found so far...
                  </div>
                )}
              </div>

              <div className="md:hidden space-y-4">
                {filtered.map((biz, idx) => {
                  const hoursList = formatOpeningHours(biz.opening_hours);
                  return (
                    <div
                      key={biz.place_id || idx}
                      onClick={() => goToDetail(biz)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && goToDetail(biz)}
                      className="bg-white/90 backdrop-blur rounded-2xl shadow-lg shadow-slate-200/50 border border-slate-100 p-4 cursor-pointer hover:shadow-xl hover:border-indigo-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-400 animate-fade-up"
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

                {loading && (
                  <div className="flex items-center justify-center gap-2 rounded-2xl bg-white/70 border border-slate-100 py-4 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                    Fetching more businesses — {results.length} found so far...
                  </div>
                )}
              </div>

              {!loading && filtered.length === 0 && (
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