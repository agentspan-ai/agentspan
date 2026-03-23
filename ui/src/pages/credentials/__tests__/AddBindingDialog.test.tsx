import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { AddBindingDialog } from "../components/AddBindingDialog";

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

const noop = vi.fn();

describe("AddBindingDialog", () => {
  it("pre-fills store name with credential name", () => {
    render(
      <AddBindingDialog
        credentialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={noop}
        onClose={noop}
      />,
      { wrapper },
    );
    expect(screen.getByLabelText(/store name/i)).toHaveValue("GITHUB_TOKEN");
  });

  it("calls PUT /credentials/bindings/{key} on submit", async () => {
    mockFetch.mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddBindingDialog
        credentialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={onSuccess}
        onClose={noop}
      />,
      { wrapper },
    );
    // Change the logical key
    await userEvent.clear(screen.getByLabelText(/logical key/i));
    await userEvent.type(screen.getByLabelText(/logical key/i), "GH_TOKEN");
    await userEvent.click(screen.getByRole("button", { name: /add binding/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("GH_TOKEN"),
      expect.anything(),
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
