export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
export const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/simulation";
