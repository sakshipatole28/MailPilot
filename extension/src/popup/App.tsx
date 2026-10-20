import { useState } from "react";
import type { Mail } from "../shared/types";
import { Compose } from "./tabs/Compose";
import { Deadlines } from "./tabs/Deadlines";
import { Draft } from "./tabs/Draft";
import { Inbox } from "./tabs/Inbox";
import { Settings } from "./tabs/Settings";

const TABS = ["Inbox", "Deadlines", "Draft", "Compose", "Settings"] as const;
type Tab = (typeof TABS)[number];

export function App() {
  const [tab, setTab] = useState<Tab>("Inbox");
  const [selected, setSelected] = useState<Mail | null>(null);

  function openMail(mail: Mail) {
    setSelected(mail);
    setTab("Draft");
  }

  return (
    <div className="app">
      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      <main>
        {tab === "Inbox" && <Inbox onOpen={openMail} />}
        {tab === "Deadlines" && <Deadlines />}
        {tab === "Draft" && <Draft mail={selected} onChange={setSelected} />}
        {tab === "Compose" && <Compose />}
        {tab === "Settings" && <Settings />}
      </main>
      <footer>Drafts only. MailPilot never sends email.</footer>
    </div>
  );
}
