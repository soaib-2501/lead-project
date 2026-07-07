import { useState } from "react";
import api from "./services/api";

function App() {
  const [form, setForm] = useState({
    city: "",
    area: "",
    category: "",
    keyword: "",
    max_results: 20,
  });

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
      setError(
        "Search failed. Backend not reachable or scraping error occurred."
      );
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>Lead Search</h1>

      <form onSubmit={handleSearch} style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <input
          name="city"
          placeholder="City (e.g. Noida)"
          value={form.city}
          onChange={handleChange}
          required
          style={{ padding: "0.5rem", flex: "1 1 150px" }}
        />
        <input
          name="area"
          placeholder="Area (optional, e.g. Sector 62)"
          value={form.area}
          onChange={handleChange}
          style={{ padding: "0.5rem", flex: "1 1 150px" }}
        />
        <input
          name="category"
          placeholder="Category (e.g. restaurant)"
          value={form.category}
          onChange={handleChange}
          required
          style={{ padding: "0.5rem", flex: "1 1 150px" }}
        />
        <input
          name="keyword"
          placeholder="Keyword (optional)"
          value={form.keyword}
          onChange={handleChange}
          style={{ padding: "0.5rem", flex: "1 1 150px" }}
        />
        <input
          type="number"
          name="max_results"
          placeholder="Max results"
          value={form.max_results}
          onChange={handleChange}
          min={1}
          max={100}
          style={{ padding: "0.5rem", width: "120px" }}
        />
        <button type="submit" disabled={loading} style={{ padding: "0.5rem 1.5rem" }}>
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {loading && (
        <p style={{ color: "#666" }}>
          Scraping in progress — this can take 1-3 minutes depending on result count. Please wait.
        </p>
      )}

      {error && <p style={{ color: "red" }}>{error}</p>}

      {!loading && results.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #ccc" }}>
              <th style={{ padding: "0.5rem" }}>Name</th>
              <th style={{ padding: "0.5rem" }}>Category</th>
              <th style={{ padding: "0.5rem" }}>Address</th>
              <th style={{ padding: "0.5rem" }}>Phone</th>
              <th style={{ padding: "0.5rem" }}>Website</th>
              <th style={{ padding: "0.5rem" }}>Rating</th>
              <th style={{ padding: "0.5rem" }}>Reviews</th>
            </tr>
          </thead>
          <tbody>
            {results.map((biz, idx) => (
              <tr key={idx} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "0.5rem" }}>{biz.name}</td>
                <td style={{ padding: "0.5rem" }}>{biz.category}</td>
                <td style={{ padding: "0.5rem" }}>{biz.address}</td>
                <td style={{ padding: "0.5rem" }}>{biz.phone}</td>
                <td style={{ padding: "0.5rem" }}>
                  {biz.website ? (
                    <a href={biz.website} target="_blank" rel="noreferrer">
                      Visit
                    </a>
                  ) : (
                    "-"
                  )}
                </td>
                <td style={{ padding: "0.5rem" }}>{biz.rating}</td>
                <td style={{ padding: "0.5rem" }}>{biz.reviews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && !error && results.length === 0 && (
        <p style={{ color: "#999" }}>No results yet — run a search above.</p>
      )}
    </div>
  );
}

export default App;