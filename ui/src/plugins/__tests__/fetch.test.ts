import { describe, expect, it } from "vitest";
import { FetchError } from "../fetch";

describe("FetchError", () => {
  it("uses the JSON response message when available", () => {
    const error = new FetchError(
      500,
      "Internal Server Error",
      "/api/test",
      JSON.stringify({ message: "Agent execution failed" }),
      "application/json",
    );

    expect(error.message).toBe("HTTP 500: Agent execution failed");
  });

  it("falls back to the HTTP status text for non-JSON responses", () => {
    const error = new FetchError(
      404,
      "Not Found",
      "/api/test",
      "not-json",
      "text/plain",
    );

    expect(error.message).toBe("HTTP 404: Not Found");
  });
});
