import { BrowserRouter, Routes, Route } from "react-router-dom";
import SearchPage from "./pages/SearchPage";
import BusinessDetailPage from "./pages/BusinessDetailPage";
import OsintHome from "./pages/osint/OsintHome";
import OsintResults from "./pages/osint/OsintResults";
import { SearchProvider } from "./context/SearchContext";

function App() {
  return (
    <BrowserRouter>
      <SearchProvider>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/business/:slug" element={<BusinessDetailPage />} />
          <Route path="/osint" element={<OsintHome />} />
          <Route path="/osint/results" element={<OsintResults />} />
        </Routes>
      </SearchProvider>
    </BrowserRouter>
  );
}

export default App;