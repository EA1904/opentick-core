import { create } from "zustand";

interface WorkspacePanel {
  id: string;
  type: "chart" | "dom" | "watchlist" | "journal" | "analytics";
  title: string;
  width: number; // percentage
}

interface AppState {
  activeSymbol: string;
  activeTimeframe: string;
  token: string | null;
  user: { email: string } | null;
  panels: WorkspacePanel[];
  
  setActiveSymbol: (symbol: string) => void;
  setActiveTimeframe: (timeframe: string) => void;
  setToken: (token: string | null) => void;
  setUser: (user: { email: string } | null) => void;
  setPanels: (panels: WorkspacePanel[]) => void;
  logout: () => void;
}

export const useStore = create<AppState>((set) => ({
  activeSymbol: "AAPL",
  activeTimeframe: "D1",
  token: typeof window !== "undefined" ? localStorage.getItem("token") : null,
  user: null,
  panels: [
    { id: "p1", type: "watchlist", title: "Watchlist", width: 25 },
    { id: "p2", type: "chart", title: "Charts", width: 50 },
    { id: "p3", type: "dom", title: "SuperDOM", width: 25 },
  ],
  
  setActiveSymbol: (symbol) => set({ activeSymbol: symbol.toUpperCase() }),
  setActiveTimeframe: (timeframe) => set({ activeTimeframe: timeframe }),
  setToken: (token) => {
    if (token) {
      localStorage.setItem("token", token);
    } else {
      localStorage.removeItem("token");
    }
    set({ token });
  },
  setUser: (user) => set({ user }),
  setPanels: (panels) => set({ panels }),
  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, user: null });
  },
}));
