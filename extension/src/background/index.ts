// Service worker: syncs mail every few minutes and keeps reminder alarms and the
// "due today" badge in sync with the backend.
import { api } from "../shared/api";
import { dueTodayCount, parseAlarmName, plannedAlarms } from "../shared/reminders";
import type { Deadline } from "../shared/types";

const REFRESH = "refresh-deadlines";
const SYNC = "sync-mail";
const SYNC_MINUTES = 5;

async function refresh(): Promise<void> {
  let deadlines: Deadline[];
  try {
    deadlines = await api.deadlines();
  } catch {
    await chrome.action.setBadgeText({ text: "" });
    return; // backend offline: keep the alarms we already have
  }
  await chrome.storage.local.set({ deadlines });

  const existing = await chrome.alarms.getAll();
  await Promise.all(
    existing.filter((a) => a.name.startsWith("dl:")).map((a) => chrome.alarms.clear(a.name)),
  );
  for (const alarm of plannedAlarms(deadlines, Date.now())) {
    await chrome.alarms.create(alarm.name, { when: alarm.when });
  }

  const today = dueTodayCount(deadlines, new Date());
  await chrome.action.setBadgeBackgroundColor({ color: "#c2410c" });
  await chrome.action.setBadgeText({ text: today ? String(today) : "" });
}

async function notify(alarmName: string): Promise<void> {
  const parsed = parseAlarmName(alarmName);
  if (!parsed) return;
  const { deadlines = [] } = (await chrome.storage.local.get("deadlines")) as {
    deadlines?: Deadline[];
  };
  const deadline = deadlines.find((d) => d.id === parsed.id);
  if (!deadline || deadline.done) return;
  const when = parsed.label === "24h" ? "in 24 hours" : "in 2 hours";
  chrome.notifications.create(alarmName, {
    type: "basic",
    iconUrl: "icon-128.png",
    title: `Due ${when}: ${deadline.title}`,
    message: deadline.mail_subject ?? "",
  });
}

// Pull new mail from the backend's mail source (Gmail or file) and tell the user about it.
async function syncMail(): Promise<void> {
  try {
    const result = await api.sync();
    if (result.new > 0) {
      chrome.notifications.create(`sync:${Date.now()}`, {
        type: "basic",
        iconUrl: "icon-128.png",
        title: `MailPilot: ${result.new} new mail${result.new > 1 ? "s" : ""}`,
        message: "Open MailPilot to see categories and draft replies.",
      });
    }
  } catch {
    // backend offline or mail source unavailable: try again at the next alarm
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(REFRESH, { periodInMinutes: 30 });
  chrome.alarms.create(SYNC, { periodInMinutes: SYNC_MINUTES });
  syncMail().then(refresh);
});
chrome.runtime.onStartup.addListener(refresh);

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === REFRESH) refresh();
  else if (alarm.name === SYNC) syncMail();
  else notify(alarm.name);
});

// The popup asks for a refresh after it adds or completes deadlines.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "refresh-deadlines") {
    refresh().then(() => sendResponse({ ok: true }));
    return true; // keep the channel open for the async response
  }
});
