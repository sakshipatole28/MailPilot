import { describe, expect, it } from "vitest";
import { dueState, dueTodayCount, parseAlarmName, plannedAlarms } from "./reminders";
import { keyForModel, providerForModel } from "./storage";
import type { Deadline } from "./types";

const HOUR = 3600 * 1000;

function deadline(id: number, due: Date | null, done = false): Deadline {
  return {
    id,
    mail_id: "m1",
    title: "t",
    due_iso: due ? due.toISOString() : null,
    confidence: 1,
    evidence: "",
    done,
    mail_subject: null,
  };
}

describe("reminders", () => {
  const now = new Date(2026, 9, 20, 9, 0); // 20 Oct 2026, 09:00 local time

  it("plans 24h and 2h alarms only in the future and skips done items", () => {
    const soon = deadline(1, new Date(now.getTime() + 5 * HOUR)); // 24h mark already passed
    const later = deadline(2, new Date(now.getTime() + 48 * HOUR));
    const done = deadline(3, new Date(now.getTime() + 48 * HOUR), true);
    const names = plannedAlarms([soon, later, done], now.getTime()).map((a) => a.name);
    expect(names).toEqual(["dl:1:2h", "dl:2:24h", "dl:2:2h"]);
  });

  it("parses alarm names", () => {
    expect(parseAlarmName("dl:12:24h")).toEqual({ id: 12, label: "24h" });
    expect(parseAlarmName("refresh-deadlines")).toBeNull();
  });

  it("counts open items due today and labels states", () => {
    const today = deadline(1, new Date(2026, 9, 20, 18, 0));
    const tomorrow = deadline(2, new Date(2026, 9, 21, 18, 0));
    const past = deadline(3, new Date(2026, 9, 19, 18, 0));
    const doneToday = deadline(4, new Date(2026, 9, 20, 18, 0), true);
    expect(dueTodayCount([today, tomorrow, past, doneToday], now))
      .toBe(1);
    expect(dueState(today, now)).toBe("today");
    expect(dueState(tomorrow, now)).toBe("upcoming");
    expect(dueState(past, now)).toBe("overdue");
  });

  it("ignores undated to-dos for alarms and the badge", () => {
    const todo = deadline(9, null);
    expect(plannedAlarms([todo], now.getTime())).toEqual([]);
    expect(dueTodayCount([todo], now)).toBe(0);
    expect(dueState(todo, now)).toBe("undated");
  });
});

describe("storage helpers", () => {
  it("maps models to providers and keys", () => {
    expect(providerForModel("gemini/gemini-2.5-flash")).toBe("gemini");
    expect(providerForModel("anthropic/claude-sonnet-4-5")).toBe("anthropic");
    expect(providerForModel("gpt-4o-mini")).toBe("openai");
    expect(providerForModel("ollama/qwen2.5:7b")).toBeNull();
    expect(keyForModel("groq/llama-3.3-70b-versatile", { groq: "gk" })).toBe("gk");
    expect(keyForModel("ollama/qwen2.5:7b", { groq: "gk" })).toBeUndefined();
  });
});
