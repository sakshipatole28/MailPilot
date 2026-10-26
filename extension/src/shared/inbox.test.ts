import { describe, expect, it } from "vitest";
import { inView, scoreClass, sortMails, unsubscribeUrl } from "./inbox";
import type { Mail } from "./types";

function mail(id: string, extra: Partial<Mail> = {}): Mail {
  return {
    id, sender: "a@b.com", sender_name: "", subject: "s", body: "", received_at: "2026-10-20T10:00:00Z",
    is_read: false, replied: false, category: null, priority: null, needs_reply: null,
    classified_by: null, headers: {}, labels: [], links: [], summary: "", intents: [],
    priority_score: null, priority_reasons: [], risk_level: null, risk_reasons: [],
    triage_status: null, ...extra,
  };
}

describe("inbox views", () => {
  it("filters by intent, priority and risk", () => {
    const replyMail = mail("1", { needs_reply: true, intents: ["reply"] });
    const replied = mail("2", { needs_reply: true, replied: true });
    const meeting = mail("3", { intents: ["meeting"], priority_score: 75 });
    const phish = mail("4", { risk_level: "high" });
    const all = [replyMail, replied, meeting, phish];
    expect(all.filter((m) => inView(m, "reply")).map((m) => m.id)).toEqual(["1"]);
    expect(all.filter((m) => inView(m, "meetings")).map((m) => m.id)).toEqual(["3"]);
    expect(all.filter((m) => inView(m, "important")).map((m) => m.id)).toEqual(["3"]);
    expect(all.filter((m) => inView(m, "suspicious")).map((m) => m.id)).toEqual(["4"]);
    expect(all.filter((m) => inView(m, "all"))).toHaveLength(4);
  });

  it("sorts by priority with untriaged mail last", () => {
    const sorted = sortMails(
      [
        mail("old-untriaged", { received_at: "2026-10-01T00:00:00Z" }),
        mail("low", { priority_score: 10 }),
        mail("high", { priority_score: 90 }),
        mail("new-untriaged", { received_at: "2026-10-25T00:00:00Z" }),
      ],
      "priority",
    );
    expect(sorted.map((m) => m.id)).toEqual(["high", "low", "new-untriaged", "old-untriaged"]);
  });

  it("finds the https unsubscribe link and classes scores", () => {
    const m = mail("1", { headers: { list_unsubscribe: "<mailto:u@x.io>, <https://x.io/u?id=1>" } });
    expect(unsubscribeUrl(m)).toBe("https://x.io/u?id=1");
    expect(unsubscribeUrl(mail("2", { headers: { list_unsubscribe: "<mailto:u@x.io>" } }))).toBeNull();
    expect(scoreClass(80)).toBe("score high");
    expect(scoreClass(null)).toBe("score none");
  });
});
