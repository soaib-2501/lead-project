import { createContext, useContext, useState } from "react";

// Lives above <Routes> in App.jsx so it never unmounts when navigating
// between SearchPage and BusinessDetailPage — that's what keeps search
// results alive when the user clicks "Back to results".
const SearchContext = createContext(null);

export function SearchProvider({ children }) {
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

  const value = {
    form,
    setForm,
    results,
    setResults,
    filtered,
    setFiltered,
    loading,
    setLoading,
    error,
    setError,
  };

  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>;
}

export function useSearchContext() {
  const ctx = useContext(SearchContext);
  if (!ctx) {
    throw new Error("useSearchContext must be used within a SearchProvider");
  }
  return ctx;
}