import { describe, expect, it } from "vitest";
import { dueLabel, hueFor, initials, matchesSearch, timeAgo } from "./format";

describe("format helpers", () => {
  const now = new Date(2026, 9, 20, 12, 0);

  it("formats relative times", () => {
    expect(timeAgo(new Date(2026, 9, 20, 11, 59, 30).toISOString(), now)).toBe("now");
    expect(timeAgo(new Date(2026, 9, 20, 11, 15).toISOString(), now)).toBe("45m");
    expect(timeAgo(new Date(2026, 9, 20, 9, 0).toISOString(), now)).toBe("3h");
    expect(timeAgo(new Date(2026, 9, 18, 12, 0).toISOString(), now)).toBe("2d");
    expect(timeAgo(new Date(2026, 8, 1).toISOString(), now)).not.toMatch(/d$/);
  });

  it("makes initials and stable colors", () => {
    expect(initials("Priya Nair")).toBe("PN");
    expect(initials("Dr. Meera Desai")).toBe("DD");
    expect(initials("", "tpo@westbrook.edu")).toBe("T");
    expect(hueFor("a@b.com")).toBe(hueFor("a@b.com"));
  });

  it("labels near due dates in words", () => {
    expect(dueLabel(new Date(2026, 9, 20, 18, 0).toISOString(), now)).toMatch(/^Today/);
    expect(dueLabel(new Date(2026, 9, 21, 9, 0).toISOString(), now)).toMatch(/^Tomorrow/);
    expect(dueLabel(new Date(2026, 9, 25, 9, 0).toISOString(), now)).not.toMatch(/^(Today|Tomorrow)/);
  });

  it("searches subject, sender and summary", () => {
    const mail = { subject: "Interview schedule", sender: "priya@northwind.com", sender_name: "Priya", summary: "Pick a slot" };
    expect(matchesSearch(mail, "INTERVIEW")).toBe(true);
    expect(matchesSearch(mail, "northwind")).toBe(true);
    expect(matchesSearch(mail, "slot")).toBe(true);
    expect(matchesSearch(mail, "exam")).toBe(false);
    expect(matchesSearch(mail, "  ")).toBe(true);
  });
});
