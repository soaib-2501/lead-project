import { BrowserRouter, Routes, Route } from "react-router-dom";
import SearchPage from "./pages/SearchPage";
import BusinessDetailPage from "./pages/BusinessDetailPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/business/:slug" element={<BusinessDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;