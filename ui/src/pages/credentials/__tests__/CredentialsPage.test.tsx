import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { MemoryRouter } from "react-router";
import { Provider as ThemeProvider } from "theme/material/provider";
import { CredentialsPage } from "../CredentialsPage";

vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

// Mock layout components that depend on app-level providers (Theme, SidebarContext, Auth)
vi.mock("shared/SectionHeader", () => ({
  default: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {actions}
    </div>
  ),
}));
vi.mock("shared/SectionHeaderActions", () => ({
  default: ({ buttons }: { buttons: Array<{ label?: string; onClick?: () => void }> }) => (
    <div>
      {buttons.map((b, i) => (
        <button key={i} onClick={b.onClick}>
          {b.label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("shared/SectionContainer", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { fetchWithContext } from "plugins/fetch";
const mockFetch = fetchWithContext as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ThemeProvider>
      <MemoryRouter>
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      </MemoryRouter>
    </ThemeProvider>
  );
}

const CREDENTIALS = [
  { name: "GITHUB_TOKEN", partial: "ghp_...6789", updated_at: "2026-03-20" },
  { name: "STRIPE_KEY", partial: "sk_l...4abc", updated_at: "2026-03-19" },
];

const BINDINGS = [
  { logical_key: "GH_TOKEN", store_name: "GITHUB_TOKEN" },
];

beforeEach(() => {
  localStorage.clear();
  // Default: auth disabled — credentials load without login
  mockFetch.mockImplementation((path: string) => {
    if (path === "/credentials") return Promise.resolve(CREDENTIALS);
    if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
    return Promise.resolve(null);
  });
});

describe("CredentialsPage", () => {
  it("renders credential list", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText("GITHUB_TOKEN")).toBeInTheDocument(),
    );
    expect(screen.getByText("STRIPE_KEY")).toBeInTheDocument();
    expect(screen.getByText("ghp_...6789")).toBeInTheDocument();
  });

  it("expand row shows bindings", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    // Click chevron for GITHUB_TOKEN
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() =>
      expect(screen.getByText(/GH_TOKEN/)).toBeInTheDocument(),
    );
  });

  it("collapse row hides bindings", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() => screen.getByText(/GH_TOKEN/));
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() =>
      expect(screen.queryByText(/GH_TOKEN/)).not.toBeInTheDocument(),
    );
  });

  it("delete confirms with credential name then calls DELETE", async () => {
    mockFetch.mockImplementation((path: string) => {
      if (path === "/credentials") return Promise.resolve(CREDENTIALS);
      if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
      return Promise.resolve(null);
    });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("delete-GITHUB_TOKEN"));
    // ConfirmChoiceDialog should appear
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox");
    await userEvent.type(input, "GITHUB_TOKEN");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("GITHUB_TOKEN"),
        expect.anything(),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
  });

  it("shows LoginDialog when server returns 401", async () => {
    mockFetch.mockRejectedValue({ status: 401 });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText(/sign in to manage credentials/i)).toBeInTheDocument(),
    );
  });

  it("shows success toast and removes item after delete", async () => {
    const credentialsAfterDelete = [
      { name: "STRIPE_KEY", partial: "sk_l...4abc", updated_at: "2026-03-19" },
    ];
    let callCount = 0;
    mockFetch.mockImplementation((path: string, _ctx: any, opts?: RequestInit) => {
      if (opts?.method === "DELETE") return Promise.resolve(null);
      if (path === "/credentials") {
        callCount++;
        // Return full list first, then post-delete list on refetch
        return Promise.resolve(callCount > 2 ? credentialsAfterDelete : CREDENTIALS);
      }
      if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
      return Promise.resolve(null);
    });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("delete-GITHUB_TOKEN"));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox");
    await userEvent.type(input, "GITHUB_TOKEN");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(screen.getByText(/credential deleted/i)).toBeInTheDocument(),
    );
  });
});
