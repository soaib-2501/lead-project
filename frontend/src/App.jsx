import { useState, useEffect } from "react";
import api from "./services/api";
import FilterPanel from "./components/FilterPanel";

function App() {
  const [form, setForm] = useState({
    city: "",
    area: "",
    category: "",
    keyword: "",
    max_results: 20,
  });

  const [results, setResults] = useState([]);
  const [filtered, setFiltered] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setFiltered(results);
  }, [results]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    console.log("[App] Search submitted:", form);

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const response = await api.post("/api/search", {
        ...form,
        max_results: Number(form.max_results),
      });
      console.log(`[App] Search succeeded — ${response.data.length} results`);
      setResults(response.data);
    } catch (err) {
      console.error("[App] Search failed:", err);
      setError("Search failed. Backend not reachable or scraping error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const formatOpeningHours = (raw) => {
    if (!raw) return null;
    return raw.split("|").map((line) => line.trim()).filter(Boolean);
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="text-center text-3xl sm:text-4xl font-bold text-gray-900 mb-8">
          Lead Search
        </h1>

        {/* Search Form */}
        <form
          onSubmit={handleSearch}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 mb-6 bg-white p-4 rounded-xl shadow-sm"
        >
          <input
            name="city"
            placeholder="City (e.g. Noida)"
            value={form.city}
            onChange={handleChange}
            required
            className="border rounded-lg px-3 py-2 lg:col-span-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            name="area"
            placeholder="Area (optional, e.g. Sector 62)"
            value={form.area}
            onChange={handleChange}
            className="border rounded-lg px-3 py-2 lg:col-span-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            name="category"
            placeholder="Category (e.g. restaurant)"
            value={form.category}
            onChange={handleChange}
            required
            className="border rounded-lg px-3 py-2 lg:col-span-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            name="keyword"
            placeholder="Keyword (optional)"
            value={form.keyword}
            onChange={handleChange}
            className="border rounded-lg px-3 py-2 lg:col-span-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            name="max_results"
            placeholder="Max results"
            value={form.max_results}
            onChange={handleChange}
            min={1}
            max={100}
            className="border rounded-lg px-3 py-2 lg:col-span-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-medium rounded-lg px-4 py-2 lg:col-span-1 transition-colors"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {loading && (
          <p className="text-gray-500 text-sm mb-4">
            Scraping in progress — this can take 1-3 minutes depending on result count. Please wait.
          </p>
        )}

        {error && (
          <p className="text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2 mb-4">
            {error}
          </p>
        )}

        {!loading && results.length > 0 && (
          <>
            <FilterPanel results={results} onFilteredChange={setFiltered} />

            <p className="text-gray-500 text-sm mb-3">
              Showing {filtered.length} of {results.length} results
            </p>

            {/* Desktop/tablet: table view */}
            <div className="hidden md:block overflow-x-auto bg-white rounded-xl shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b bg-gray-50 text-gray-600">
                    <th className="p-3">Name</th>
                    <th className="p-3">Category</th>
                    <th className="p-3">Address</th>
                    <th className="p-3">Phone</th>
                    <th className="p-3">Website</th>
                    <th className="p-3 text-center">Rating</th>
                    <th className="p-3 text-center">Reviews</th>
                    <th className="p-3 min-w-[220px]">Opening Hours</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((biz, idx) => {
                    const hoursList = formatOpeningHours(biz.opening_hours);
                    return (
                      <tr key={idx} className="border-b align-top hover:bg-gray-50">
                        <td className="p-3 font-semibold text-gray-900">{biz.name}</td>
                        <td className="p-3 text-gray-700">{biz.category || "-"}</td>
                        <td className="p-3 text-gray-700">{biz.address || "-"}</td>
                        <td className="p-3 text-gray-700">{biz.phone || "-"}</td>
                        <td className="p-3">
                          {biz.website ? (
                            <a href={biz.website} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                              Visit
                            </a>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="p-3 text-center">
                          {biz.rating !== null && biz.rating !== undefined ? `⭐ ${biz.rating}` : "N/A"}
                        </td>
                        <td className="p-3 text-center">{biz.reviews}</td>
                        <td className="p-3 text-xs text-gray-600">
                          {hoursList ? (
                            <ul className="list-disc list-inside space-y-0.5">
                              {hoursList.map((line, i) => (
                                <li key={i}>{line}</li>
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

            {/* Mobile: card view */}
            <div className="md:hidden space-y-3">
              {filtered.map((biz, idx) => {
                const hoursList = formatOpeningHours(biz.opening_hours);
                return (
                  <div key={idx} className="bg-white rounded-xl shadow-sm p-4">
                    <p className="font-semibold text-gray-900 mb-1">{biz.name}</p>
                    <p className="text-sm text-gray-600 mb-1">{biz.category || "-"}</p>
                    <p className="text-sm text-gray-600 mb-1">{biz.address || "-"}</p>
                    <p className="text-sm text-gray-600 mb-1">{biz.phone || "-"}</p>
                    <div className="flex items-center gap-3 text-sm mb-2">
                      <span>{biz.rating !== null && biz.rating !== undefined ? `⭐ ${biz.rating}` : "N/A"}</span>
                      <span className="text-gray-500">{biz.reviews} reviews</span>
                      {biz.website && (
                        <a href={biz.website} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                          Visit
                        </a>
                      )}
                    </div>
                    {hoursList && (
                      <ul className="text-xs text-gray-500 list-disc list-inside space-y-0.5">
                        {hoursList.map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>

            {filtered.length === 0 && (
              <p className="text-gray-400 mt-4 text-center">No results match these filters.</p>
            )}
          </>
        )}

        {!loading && !error && results.length === 0 && (
          <p className="text-gray-400 text-center">No results yet — run a search above.</p>
        )}
      </div>
    </div>
  );
}

export default App;