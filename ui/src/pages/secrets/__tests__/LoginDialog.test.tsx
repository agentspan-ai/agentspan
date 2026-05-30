import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { LoginDialog } from "../components/LoginDialog";

// Mock fetchWithContext so we don't need a real server
vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

import { fetchWithContext } from "plugins/fetch";
const mockFetch = fetchWithContext as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("LoginDialog", () => {
  it("renders username and password fields", () => {
    render(
      <LoginDialog onSuccess={vi.fn()} />,
      { wrapper },
    );
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows inline error on 401", async () => {
    mockFetch.mockRejectedValueOnce({ status: 401 });
    render(<LoginDialog onSuccess={vi.fn()} />, { wrapper });
    await userEvent.type(screen.getByLabelText(/username/i), "admin");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument(),
    );
  });

  it("calls onSuccess with token on 200", async () => {
    mockFetch.mockResolvedValueOnce({ token: "jwt123", user: { id: "1", username: "admin", name: "Admin" } });
    const onSuccess = vi.fn();
    render(<LoginDialog onSuccess={onSuccess} />, { wrapper });
    await userEvent.type(screen.getByLabelText(/username/i), "admin");
    await userEvent.type(screen.getByLabelText(/password/i), "agentspan");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("jwt123"));
  });
});
