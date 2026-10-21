import { describe, it, expect } from "vitest";

describe("Message type", () => {
  it("defines a valid Message shape", () => {
    const msg = {
      id: "1",
      role: "user" as const,
      content: "hello",
      createdAt: "2026-01-01T00:00:00Z",
    };
    expect(msg.role).toBe("user");
    expect(msg.content).toBe("hello");
  });
});
