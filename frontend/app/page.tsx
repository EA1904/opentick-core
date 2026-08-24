"use client";

import { useEffect, useState, useRef } from "react";
import { useStore } from "../lib/store";
import { 
  TrendingUp, 
  Settings, 
  User as UserIcon, 
  Activity, 
  Layers, 
  BookOpen, 
  BarChart2, 
  Database,
  Lock,
  Mail,
  RefreshCw,
  Play,
  CheckCircle,
  AlertCircle
} from "lucide-react";

export default function DashboardPage() {
  const { 
    activeSymbol, 
    activeTimeframe, 
    token, 
    user, 
    panels, 
    setActiveSymbol, 
    setActiveTimeframe, 
    setToken, 
    setUser 
  } = useStore();

  const [username, setUsername] = useState("admin@tradovera.local");
  const [password, setPassword] = useState("password");
  const [loginError, setLoginError] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [symbols, setSymbols] = useState<any[]>([]);
  const [isLoadingSymbols, setIsLoadingSymbols] = useState(false);
  const [wsStatus, setWsStatus] = useState("disconnected");
  
  // Real-time market feed state
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState<number>(0);

  // Authentication check & symbol fetching
  useEffect(() => {
    if (token) {
      // Decode user dummy info or fetch profile
      setUser({ email: "admin@tradovera.local" });
      fetchSymbols();
    }
  }, [token]);

  // Handle local WebSocket connections
  useEffect(() => {
    if (!token) return;
    
    let ws: WebSocket;
    try {
      ws = new WebSocket("ws://localhost:8000/ws");
      
      ws.onopen = () => {
        setWsStatus("connected");
        // Subscribe to current active symbol
        ws.send(JSON.stringify({ action: "subscribe", symbol: activeSymbol }));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.symbol === activeSymbol) {
          // If we receive custom stream data (for live simulation later)
          const data = JSON.parse(msg.data);
          if (data.price) {
            setCurrentPrice(data.price);
            setPriceChange(data.change || 0);
          }
        }
      };

      ws.onclose = () => {
        setWsStatus("disconnected");
      };

      ws.onerror = () => {
        setWsStatus("error");
      };
    } catch (e) {
      setWsStatus("error");
    }

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [token, activeSymbol]);

  const fetchSymbols = async () => {
    setIsLoadingSymbols(true);
    try {
      const res = await fetch("http://localhost:8000/api/v1/data/symbols", {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSymbols(data);
      }
    } catch (e) {
      console.error("Failed to fetch symbols from backend", e);
    } finally {
      setIsLoadingSymbols(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setIsLoggingIn(true);

    try {
      const formData = new URLSearchParams();
      formData.append("username", username);
      formData.append("password", password);

      const res = await fetch("http://localhost:8000/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
      } else {
        const errorData = await res.json();
        setLoginError(errorData.detail || "Identifiants invalides");
      }
    } catch (err) {
      setLoginError("Impossible de se connecter au serveur backend");
    } finally {
      setIsLoggingIn(false);
    }
  };

  // Mock symbols fallback if DB is not populated
  const defaultSymbols = [
    { symbol: "AAPL", longname: "Apple Inc.", asset_class: "stocks", end_date: "2026-08-14", rows_count: 1250 },
    { symbol: "MSFT", longname: "Microsoft Corp.", asset_class: "stocks", end_date: "2026-08-14", rows_count: 1250 },
    { symbol: "TSLA", longname: "Tesla Inc.", asset_class: "stocks", end_date: "2026-08-14", rows_count: 980 },
    { symbol: "BTCUSDT", longname: "Bitcoin / Tether", asset_class: "crypto", end_date: "2026-08-17", rows_count: 15400 },
    { symbol: "EURUSD", longname: "Euro / US Dollar", asset_class: "forex", end_date: "2026-08-14", rows_count: 4500 }
  ];

  const activeSymbolsList = symbols.length > 0 ? symbols : defaultSymbols;

  if (!token) {
    // Beautiful premium Login interface
    return (
      <div className="relative flex min-h-screen items-center justify-center bg-[#06070a] px-4 overflow-hidden">
        {/* Glow ambient backgrounds */}
        <div className="absolute top-1/4 left-1/4 h-96 w-96 rounded-full bg-indigo-500/10 blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 h-96 w-96 rounded-full bg-blue-500/10 blur-[120px]" />

        <div className="w-full max-w-md rounded-2xl border border-white/5 bg-white/[0.02] p-8 shadow-2xl backdrop-blur-2xl">
          <div className="mb-8 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-400">
              <TrendingUp className="h-6 w-6" />
            </div>
            <h1 className="mt-4 text-3xl font-bold tracking-tight text-white font-sans">TradoVera</h1>
            <p className="mt-2 text-sm text-gray-400">Accédez à votre espace de simulation local</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400">Adresse Email</label>
              <div className="relative mt-2">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500">
                  <Mail className="h-4 w-4" />
                </span>
                <input
                  type="email"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-xl border border-white/5 bg-white/[0.04] py-3 pl-10 pr-4 text-sm text-white placeholder-gray-500 outline-none ring-offset-0 transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="admin@tradovera.local"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-400">Mot de passe</label>
              <div className="relative mt-2">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500">
                  <Lock className="h-4 w-4" />
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-white/5 bg-white/[0.04] py-3 pl-10 pr-4 text-sm text-white placeholder-gray-500 outline-none ring-offset-0 transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            {loginError && (
              <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-3 text-xs text-red-400 border border-red-500/20">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{loginError}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoggingIn}
              className="w-full rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 active:scale-[0.98] disabled:opacity-50"
            >
              {isLoggingIn ? "Authentification..." : "Se connecter"}
            </button>
          </form>

          <div className="mt-6 text-center text-xs text-gray-500">
            Compte démo par défaut : <span className="text-gray-400">admin@tradovera.local</span> / <span className="text-gray-400">password</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[#08090d] text-gray-100 overflow-hidden font-sans">
      {/* Top Header */}
      <header className="flex h-14 items-center justify-between border-b border-[#1b1f30] bg-[#0c0e17] px-6">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <TrendingUp className="h-4 w-4" />
            </div>
            <span className="text-lg font-bold tracking-tight text-white font-sans">TradoVera</span>
          </div>
          
          {/* Active symbol information */}
          <div className="flex items-center gap-2 border-l border-white/10 pl-6">
            <span className="text-sm font-bold text-white bg-white/5 px-2 py-0.5 rounded uppercase tracking-wider">{activeSymbol}</span>
            <span className="text-xs text-gray-400">{activeTimeframe}</span>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* WS Status Indicator */}
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${wsStatus === "connected" ? "bg-green-500" : wsStatus === "error" ? "bg-red-500" : "bg-yellow-500"}`} />
            <span className="text-xs uppercase tracking-wider text-gray-400 font-semibold">{wsStatus === "connected" ? "Gateway Live" : "Déconnecté"}</span>
          </div>

          {/* Account simulated balance */}
          <div className="flex items-center gap-3 bg-white/[0.02] border border-white/5 rounded-lg px-3 py-1 text-sm">
            <span className="text-gray-400">Sim:</span>
            <span className="font-bold text-emerald-400">$100,000.00</span>
          </div>

          {/* Logout / Profile */}
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/10">
              <UserIcon className="h-4 w-4" />
            </div>
            <span className="text-xs text-gray-300 hidden md:block">admin</span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar navigation */}
        <aside className="w-16 flex-col items-center justify-between border-r border-[#1b1f30] bg-[#090b12] py-6 hidden md:flex">
          <div className="flex flex-col gap-6">
            <button className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/10 text-indigo-400 border border-indigo-500/20">
              <Layers className="h-5 w-5" />
            </button>
            <button className="flex h-10 w-10 items-center justify-center rounded-xl text-gray-500 hover:text-gray-300">
              <BookOpen className="h-5 w-5" />
            </button>
            <button className="flex h-10 w-10 items-center justify-center rounded-xl text-gray-500 hover:text-gray-300">
              <BarChart2 className="h-5 w-5" />
            </button>
            <button className="flex h-10 w-10 items-center justify-center rounded-xl text-gray-500 hover:text-gray-300">
              <Database className="h-5 w-5" />
            </button>
          </div>
          <button className="flex h-10 w-10 items-center justify-center rounded-xl text-gray-500 hover:text-gray-300">
            <Settings className="h-5 w-5" />
          </button>
        </aside>

        {/* Modular Workspace Panels */}
        <main className="flex flex-1 overflow-hidden p-4 gap-4">
          
          {/* Panel 1: Watchlist */}
          <div className="flex w-1/4 flex-col rounded-xl border border-[#1b1f30] bg-[#0c0e17] overflow-hidden">
            <div className="flex items-center justify-between border-b border-[#1b1f30] px-4 py-3 bg-[#0d0f1a]">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Watchlist</span>
              <button onClick={fetchSymbols} disabled={isLoadingSymbols} className="text-gray-500 hover:text-white transition">
                <RefreshCw className={`h-3 w-3 ${isLoadingSymbols ? "animate-spin" : ""}`} />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto divide-y divide-[#1b1f30]">
              {activeSymbolsList.map((item, idx) => (
                <div 
                  key={idx}
                  onClick={() => setActiveSymbol(item.symbol)}
                  className={`flex items-center justify-between px-4 py-3 cursor-pointer transition ${activeSymbol === item.symbol ? "bg-indigo-600/10 border-l-2 border-indigo-500" : "hover:bg-white/[0.01]"}`}
                >
                  <div>
                    <div className="text-sm font-bold text-white">{item.symbol}</div>
                    <div className="text-[10px] text-gray-500 truncate max-w-[120px]">{item.longname || "N/A"}</div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-semibold bg-white/5 text-gray-400 px-1.5 py-0.5 rounded">
                      {item.asset_class}
                    </span>
                    <div className="text-[10px] text-gray-500 mt-1">{item.rows_count} bougies</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Panel 2: Chart Area */}
          <div className="flex flex-1 flex-col rounded-xl border border-[#1b1f30] bg-[#0c0e17] overflow-hidden">
            <div className="flex items-center justify-between border-b border-[#1b1f30] px-6 py-3 bg-[#0d0f1a]">
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold text-white">{activeSymbol} Graphique</span>
                <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5">
                  {["1m", "5m", "15m", "D1"].map((tf) => (
                    <button
                      key={tf}
                      onClick={() => setActiveTimeframe(tf)}
                      className={`text-xs font-semibold px-2 py-0.5 rounded transition ${activeTimeframe === tf ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
              <div className="text-xs text-gray-500">Lightweight Charts boilerplate</div>
            </div>

            {/* TradingView Chart Container */}
            <div className="flex-1 flex items-center justify-center p-6 relative">
              <div className="absolute inset-0 gradient-glow -z-10" />
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400 mb-4 animate-pulse">
                  <Activity className="h-8 w-8" />
                </div>
                <h3 className="text-lg font-bold text-white">Visualisation Graphique</h3>
                <p className="text-sm text-gray-400 mt-2 max-w-sm">Le moteur de rendu graphique Lightweight Charts s'affichera ici lors de l'intégration finale.</p>
              </div>
            </div>
          </div>

          {/* Panel 3: DOM / SuperDOM */}
          <div className="flex w-1/4 flex-col rounded-xl border border-[#1b1f30] bg-[#0c0e17] overflow-hidden">
            <div className="flex items-center justify-between border-b border-[#1b1f30] px-4 py-3 bg-[#0d0f1a]">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Order Book / DOM</span>
              <span className="text-[10px] text-gray-500">Simulé</span>
            </div>

            <div className="flex-1 flex flex-col justify-between p-4">
              {/* Simple DOM Ladder Display mockup */}
              <div className="space-y-1">
                {[101.5, 101.2, 100.9, 100.6, 100.3].map((price, idx) => (
                  <div key={idx} className="flex justify-between text-xs px-2 py-1 rounded bg-red-500/5 border border-red-500/10">
                    <span className="text-red-400 font-bold">{price}</span>
                    <span className="text-gray-400">Ask: {5 + idx * 3}</span>
                  </div>
                ))}

                <div className="text-center py-2 border-y border-[#1b1f30] my-2">
                  <div className="text-xs text-gray-500">Dernier Prix</div>
                  <div className="text-base font-bold text-white">100.00</div>
                </div>

                {[99.7, 99.4, 99.1, 98.8, 98.5].map((price, idx) => (
                  <div key={idx} className="flex justify-between text-xs px-2 py-1 rounded bg-emerald-500/5 border border-emerald-500/10">
                    <span className="text-emerald-400 font-bold">{price}</span>
                    <span className="text-gray-400">Bid: {4 + idx * 2}</span>
                  </div>
                ))}
              </div>

              {/* Order Entry actions */}
              <div className="mt-4 pt-4 border-t border-[#1b1f30] space-y-2">
                <div className="flex gap-2">
                  <button className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition">Acheter</button>
                  <button className="flex-1 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold transition">Vendre</button>
                </div>
                <button className="w-full py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg text-xs font-semibold transition border border-white/5">
                  Annuler tous les ordres
                </button>
              </div>
            </div>
          </div>

        </main>
      </div>
    </div>
  );
}
