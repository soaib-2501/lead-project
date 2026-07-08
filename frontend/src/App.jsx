import { BrowserRouter, Routes, Route } from "react-router-dom";
import SearchPage from "./pages/SearchPage";
import BusinessDetailPage from "./pages/BusinessDetailPage";
import { SearchProvider } from "./context/SearchContext";

function App() {
  return (
    <BrowserRouter>
      <SearchProvider>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/business/:slug" element={<BusinessDetailPage />} />
        </Routes>
      </SearchProvider>
    </BrowserRouter>
  );
}

export default App;