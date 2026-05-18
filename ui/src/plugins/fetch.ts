/**
 * Fetch utilities for OSS mode.
 *
 * This simplified version removes auth token handling since
 * OSS mode does not use authentication.
 */
import { MessageContext } from "components/v1/layout/MessageContext";
import { useContext } from "react";
import { IObject } from "types/common";
import { formatHttpErrorMessage, getErrorMessage, tryToJson } from "utils/utils";
import { useEnv as hardcodeEnv } from "./env";

/**
 * Typed error class for API fetch failures.
 * Replaces throwing raw Response objects while remaining backward-compatible
 * with callers that use Response-like methods (json(), text(), clone(), headers.get()).
 */
export class FetchError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly url: string;
  public readonly body: string | null;
  public readonly contentType: string | null;

  /** Minimal headers shim for backward compat with Response.headers.get(). */
  public readonly headers: { get(name: string): string | null };

  constructor(
    status: number,
    statusText: string,
    url: string,
    body: string | null,
    contentType: string | null = null,
  ) {
    const parsedBody =
      contentType?.includes("application/json") === true
        ? tryToJson<{ message?: string }>(body)
        : undefined;
    const serverMessage =
      typeof parsedBody?.message === "string" ? parsedBody.message : statusText;

    super(formatHttpErrorMessage(status, serverMessage));
    this.name = "FetchError";
    this.status = status;
    this.statusText = statusText;
    this.url = url;
    this.body = body;
    this.contentType = contentType;

    const ct = contentType;
    this.headers = {
      get(name: string): string | null {
        if (name.toLowerCase() === "content-type") return ct;
        return null;
      },
    };
  }

  /** Parse the body as JSON. Returns a Promise for backward compat with Response.json(). */
  json(): Promise<any> {
    if (!this.body) return Promise.resolve(null);
    try {
      return Promise.resolve(JSON.parse(this.body));
    } catch {
      return Promise.resolve(null);
    }
  }

  /** Return the body as text. Returns a Promise for backward compat with Response.text(). */
  text(): Promise<string> {
    return Promise.resolve(this.body ?? "");
  }

  /** Return a clone of this error for backward compat with Response.clone(). */
  clone(): FetchError {
    return new FetchError(this.status, this.statusText, this.url, this.body, this.contentType);
  }
}

const { VITE_ENVIRONMENT, VITE_WF_SERVER } = process.env;

export function fetchContextNonHook() {
  const { stack } = hardcodeEnv();

  return {
    stack,
    ready: true,
  };
}

export function useFetchContext() {
  const contextNonHook = fetchContextNonHook();
  const { setMessage } = useContext(MessageContext);

  return {
    ...contextNonHook,
    setMessage,
  };
}

export async function fetchWithContext(
  path: string,
  context: IObject,
  fetchParams: IObject,
  isText?: boolean,
  throwOnError = true,
): Promise<any> {
  const newParams = { ...fetchParams };

  // Need for build version (can't use proxy)
  const newPath = `${
    VITE_ENVIRONMENT === "test" ? VITE_WF_SERVER : ""
  }/api/${path}`;

  const cleanPath = newPath.replace(/([^:]\/)\/+/g, "$1"); // Cleanup duplicated slashes

  const res = await fetch(cleanPath, newParams);

  // Handle error cases
  if (!res.ok) {
    const hasContext = context && context?.setMessage != null;
    // 1. Using global message
    if (hasContext && !throwOnError) {
      const errorMessage = await getErrorMessage(res);
      context.setMessage({ text: errorMessage, severity: "error" });

      return null;
    }

    // 2. Throw a typed error for local handling
    const errorContentType = res.headers.get("content-type");
    const errorBody = await res.text().catch(() => null);
    throw new FetchError(res.status, res.statusText, cleanPath, errorBody, errorContentType);
  }

  const text = await res.text();

  if (!text || text.length === 0) {
    return null;
  }

  return isText ? text : tryToJson(text);
}
