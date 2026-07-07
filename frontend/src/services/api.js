import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000",
});

api.interceptors.request.use(
  (config) => {
    console.log(`[API →] ${config.method.toUpperCase()} ${config.baseURL}${config.url}`, config.data ?? "");
    return config;
  },
  (error) => {
    console.error("[API] Request setup failed:", error.message);
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => {
    console.log(`[API ←] ${response.status} ${response.config.url}`, response.data);
    return response;
  },
  (error) => {
    if (error.response) {
      // Server responded with an error status (4xx, 5xx)
      console.error(
        `[API ✗] ${error.response.status} ${error.config?.url}`,
        error.response.data
      );
    } else if (error.request) {
      // Request went out, no response (backend down, CORS block, network fail)
      console.error("[API ✗] No response received — backend unreachable?", error.message);
    } else {
      console.error("[API ✗] Error setting up request:", error.message);
    }
    return Promise.reject(error);
  }
);

export default api;