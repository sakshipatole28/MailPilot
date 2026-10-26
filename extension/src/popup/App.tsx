import { useState } from "react";
import type { Mail } from "../shared/types";
import { Ask } from "./tabs/Ask";
import { Compose } from "./tabs/Compose";
import { Draft } from "./tabs/Draft";
import { Inbox } from "./tabs/Inbox";
import { Settings } from "./tabs/Settings";
import { Tasks } from "./tabs/Tasks";

const TABS = ["Inbox", "Tasks", "Draft", "Ask", "Compose", "Settings"] as const;
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
        {tab === "Tasks" && <Tasks />}
        {tab === "Draft" && <Draft mail={selected} onChange={setSelected} />}
        {tab === "Ask" && <Ask onOpen={openMail} />}
        {tab === "Compose" && <Compose />}
        {tab === "Settings" && <Settings />}
      </main>
      <footer>Drafts only. MailPilot never sends email.</footer>
    </div>
  );
}
