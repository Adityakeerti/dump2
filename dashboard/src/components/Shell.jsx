import { Bell, Bot, BrainCircuit, Building2, Landmark, LayoutGrid, MessageSquare, Moon, Search, Siren, Sun, Users } from "lucide-react";

export const PAGES = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { id: "policy", label: "Policy Lab", icon: BrainCircuit },
  { id: "residents", label: "Residents", icon: Users },
  { id: "civic", label: "Civic Sim", icon: Landmark },
  { id: "townhall", label: "TownHall", icon: Building2 },
  { id: "tickets", label: "Tickets", icon: Siren },
  { id: "messages", label: "Messages", icon: MessageSquare },
];

export function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <path fill="var(--green)" d="M16 2l3.2 9.2L28 8l-5.6 8L28 24l-8.8-3.2L16 30l-3.2-9.2L4 24l5.6-8L4 8l8.8 3.2z" />
      <circle cx="16" cy="16" r="4" fill="var(--peach)" />
    </svg>
  );
}

export function Sidebar({ page, setPage }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="brand"><Logo /> CitySense</div>
      {PAGES.map(({ id, label, icon: Icon }, i) => (
        <span key={id} style={{ display: "contents" }}>
          {i === 4 && <div className="nav-sep" />}
          <button className={`nav-btn${page === id ? " on" : ""}`} onClick={() => setPage(id)} aria-current={page === id ? "page" : undefined}>
            <Icon size={17} /> {label}
          </button>
        </span>
      ))}
      <div className="side-foot">
        Twin data is <b>simulated</b> (CTM corridor). Agent plans come from a local Gemma model.
      </div>
    </nav>
  );
}

export function Topbar({ theme, setTheme, services, unread, onBell, query, setQuery }) {
  return (
    <header className="topbar">
      <label className="search">
        <Search size={16} className="muted" />
        <input placeholder="Search activity…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search activity" />
      </label>
      <button className="round-btn" onClick={onBell} aria-label="Notifications">
        <Bell size={17} />{unread > 0 && <span className="badge-dot">{unread > 99 ? "99+" : unread}</span>}
      </button>
      <div className="pills">
        {services.map((s) => (
          <span className="pill" key={s.name} title={s.detail || ""}><span className={`dot ${s.state}`} />{s.name}</span>
        ))}
      </div>
      <div className="theme-toggle" role="group" aria-label="Theme">
        <button className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")} aria-label="Dark theme"><Moon size={15} /></button>
        <button className={theme !== "dark" ? "on" : ""} onClick={() => setTheme("light")} aria-label="Light theme"><Sun size={15} /></button>
      </div>
      <div className="user-chip">
        <span className="avatar" style={{ background: "var(--green)" }}><Bot size={15} /></span>
        <span>City Operator</span>
      </div>
    </header>
  );
}
