import { type ReactNode, useEffect, useState } from "react";
import { api } from "../shared/api";
import type { Mail } from "../shared/types";
import { AskIcon, ComposeIcon, InboxIcon, LogoMark, SettingsIcon, TasksIcon } from "./icons";
import { Ask } from "./tabs/Ask";
import { Compose } from "./tabs/Compose";
import { Draft } from "./tabs/Draft";
import { Inbox } from "./tabs/Inbox";
import { Settings } from "./tabs/Settings";
import { Tasks } from "./tabs/Tasks";

type Tab = "Inbox" | "Tasks" | "Ask" | "Compose" | "Settings";
const NAV: { id: Tab; icon: () => ReactNode }[] = [
  { id: "Inbox", icon: InboxIcon },
  { id: "Tasks", icon: TasksIcon },
  { id: "Ask", icon: AskIcon },
  { id: "Compose", icon: ComposeIcon },
  { id: "Settings", icon: SettingsIcon },
];

/** Shown when the backend is not running: the one command that fixes it, and Retry. */
function Offline({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="offline">
      <div className="empty-emoji" aria-hidden="true">🔌</div>
      <div className="empty-title">MailPilot's backend isn't running</div>
      <p className="muted">Start it in a terminal, then press Retry:</p>
      <pre className="code">cd ~/MailPilot/backend{"\n"}.venv/bin/uvicorn app.main:app --port 8000</pre>
      <button className="primary" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function App() {
  const [tab, setTab] = useState<Tab>("Inbox");
  const [selected, setSelected] = useState<Mail | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  async function check() {
    setOnline(null);
    setOnline(await api.health().then(() => true, () => false));
  }

  useEffect(() => {
    check();
  }, []);

  function go(next: Tab) {
    setSelected(null); // leaving a mail returns to the list
    setTab(next);
  }

  let screen: ReactNode;
  if (online === false) screen = <Offline onRetry={check} />;
  else if (selected) screen = <Draft mail={selected} onChange={setSelected} onBack={() => setSelected(null)} />;
  else if (tab === "Inbox") screen = <Inbox onOpen={setSelected} />;
  else if (tab === "Tasks") screen = <Tasks />;
  else if (tab === "Ask") screen = <Ask onOpen={setSelected} />;
  else if (tab === "Compose") screen = <Compose />;
  else screen = <Settings />;

  return (
    <div className="app">
      <header className="topbar">
        <LogoMark />
        <span className="brand">MailPilot</span>
        <span className={`status-dot ${online ? "on" : online === false ? "off" : ""}`}
          title={online ? "Backend connected" : "Backend not reachable"} />
        <span className="topbar-note">drafts only · never sends</span>
      </header>
      <main key={selected ? `mail-${selected.id}` : tab} className="screen">{screen}</main>
      <nav className="bottomnav">
        {NAV.map(({ id, icon: NavIcon }) => (
          <button key={id} className={!selected && tab === id ? "active" : ""} onClick={() => go(id)}>
            <NavIcon />
            <span>{id}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
