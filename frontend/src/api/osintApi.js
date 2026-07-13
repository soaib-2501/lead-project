import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function searchOsint(payload) {
  const { data } = await axios.post(`${API_BASE}/api/osint/search`, payload);
  return data;
}