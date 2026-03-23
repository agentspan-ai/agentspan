import "@testing-library/jest-dom";
import { vi } from "vitest";

// Node.js v25+ ships a native `localStorage` global that does not implement
// the Web Storage API (no getItem/setItem/removeItem/clear/key/length).
// This conflicts with jsdom's implementation in Vitest's jsdom environment.
// Replace both storage globals with isolated spec-compliant in-memory instances.
function makeStorageMock(): Storage {
  const store: Record<string, string> = {};
  return {
    get length() {
      return Object.keys(store).length;
    },
    clear() {
      Object.keys(store).forEach((k) => delete store[k]);
    },
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key)
        ? store[key]
        : null;
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
    removeItem(key: string) {
      delete store[key];
    },
    key(index: number) {
      return Object.keys(store)[index] ?? null;
    },
  };
}
Object.defineProperty(globalThis, "localStorage", {
  value: makeStorageMock(),
  writable: true,
  configurable: true,
});
Object.defineProperty(globalThis, "sessionStorage", {
  value: makeStorageMock(),
  writable: true,
  configurable: true,
});

// Monaco Editor calls document.queryCommandSupported during module init,
// which jsdom does not implement. Stub it out globally.
Object.defineProperty(document, "queryCommandSupported", {
  value: vi.fn(() => false),
  writable: true,
});

// Monaco Editor does not run in jsdom. Mock the package so tests that render
// components containing editors get a lightweight no-op instead.
vi.mock("@monaco-editor/react", () => ({
  default: vi.fn(() => null),
  Editor: vi.fn(() => null),
  DiffEditor: vi.fn(() => null),
  useMonaco: vi.fn(() => null),
  loader: { config: vi.fn() },
}));
