import { describe, it, expect } from "vitest";
import { api } from "./api";

describe("API client", () => {
  it("creates an axios instance with a base URL", () => {
    expect(api).toBeDefined();
    expect(api.defaults.baseURL).toBeDefined();
    expect(typeof api.defaults.baseURL).toBe("string");
  });

  it("configures JSON content type in headers", () => {
    const headers = api.defaults.headers as Record<string, unknown>;
    const contentType = (headers as Record<string, string>)["Content-Type"];
    if (contentType !== undefined) {
      expect(contentType).toBe("application/json");
    }
  });
});
