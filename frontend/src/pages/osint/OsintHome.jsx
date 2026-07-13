import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { searchOsint } from "../../api/osintApi";

const STATUS_MESSAGES = [
  "Searching Google...",
  "Finding LinkedIn...",
  "Collecting public information...",
  "Analyzing results...",
  "Preparing report...",
];

export default function OsintHome() {
  const { state, key } = useLocation();
  const prefill = state?.prefill;

  const [businessName, setBusinessName] = useState(prefill?.business_name || "");
  const [locationValue, setLocationValue] = useState(prefill?.location || "");
  const [address, setAddress] = useState(prefill?.address || "");
  const [loading, setLoading] = useState(false);
  const [statusIndex, setStatusIndex] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (prefill?.business_name) {
      setBusinessName(prefill.business_name);
      setLocationValue(prefill.location || "");
      setAddress(prefill.address || "");
    }
  }, [prefill]);

  // Goes back to wherever this page was opened from (usually the business
  // detail page). Falls back to the search page if opened directly with
  // no history in this app (refresh or a shared link).
  const handleBack = () => {
    if (key !== "default") {
      navigate(-1);
    } else {
      navigate("/");
    }
  };

  const runSearch = async (name, loc, addr) => {
    setLoading(true);
    const interval = setInterval(() => {
      setStatusIndex((i) => (i + 1) % STATUS_MESSAGES.length);
    }, 1500);

    try {
      const data = await searchOsint({
        business_name: name,
        location: loc,
        address: addr || null,
      });
      navigate("/osint/results", { state: { data } });
    } catch (err) {
      alert("Search failed. Is the backend running on port 8000?");
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!businessName.trim() || !locationValue.trim()) return;
    await runSearch(businessName, locationValue, address);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-xl -mt-4 mb-4">
        <button
          onClick={handleBack}
          className="inline-flex items-center gap-2 text-gray-500 hover:text-indigo-600 text-sm font-medium transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
      </div>

      <h1 className="text-4xl font-bold text-gray-800 mb-2">Business OSINT Search</h1>
      <p className="text-gray-500 mb-8">Public, open-source business intelligence lookup</p>

      {prefill?.business_name && (
        <p className="text-sm text-indigo-600 mb-4 -mt-4">
          Pre-filled from lead search — edit if needed, then hit Search.
        </p>
      )}

      <form onSubmit={handleSearch} className="w-full max-w-xl bg-white shadow-lg rounded-2xl p-6 space-y-4">
        <input
          type="text"
          placeholder="Business Name"
          value={businessName}
          onChange={(e) => setBusinessName(e.target.value)}
          className="w-full border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <input
          type="text"
          placeholder="Location (city, state)"
          value={locationValue}
          onChange={(e) => setLocationValue(e.target.value)}
          className="w-full border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <input
          type="text"
          placeholder="Address (optional)"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          className="w-full border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white font-medium rounded-xl py-3 hover:bg-indigo-700 transition disabled:opacity-60"
        >
          {loading ? STATUS_MESSAGES[statusIndex] : "Search"}
        </button>
      </form>
    </div>
  );
}