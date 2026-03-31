import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "react-query";
import getTheme from "theme/theme";
import { AddEditCredentialDialog } from "../components/AddEditCredentialDialog";

vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

const theme = getTheme("light");

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}

const noop = vi.fn();

describe("AddEditCredentialDialog — add mode", () => {
  it("rejects blank name", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(screen.getByText(/name is required/i)).toBeInTheDocument(),
    );
  });

  it("rejects blank value", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^name/i), "GITHUB_TOKEN");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(screen.getByText(/value is required/i)).toBeInTheDocument(),
    );
  });

  it("toggles value visibility", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    const valueInput = screen.getByLabelText(/^value/i);
    expect(valueInput).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: /toggle secret visibility/i }));
    expect(valueInput).toHaveAttribute("type", "text");
  });
});

describe("AddEditCredentialDialog — edit mode", () => {
  it("name field is read-only in edit mode", () => {
    render(
      <AddEditCredentialDialog
        mode="edit"
        initialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={noop}
        onClose={noop}
      />,
      { wrapper },
    );
    expect(screen.getByLabelText(/^name/i)).toHaveAttribute("readonly");
  });
});

describe("AddEditCredentialDialog — submit paths", () => {
  it("calls POST /credentials on add submit", async () => {
    const { fetchWithContext: mockF } = await import("plugins/fetch");
    (mockF as ReturnType<typeof vi.fn>).mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={onSuccess} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^name/i), "MY_TOKEN");
    await userEvent.type(screen.getByLabelText(/^value/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockF).toHaveBeenCalledWith(
      "/credentials",
      expect.anything(),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("calls PUT /credentials/{name} on edit submit", async () => {
    const { fetchWithContext: mockF } = await import("plugins/fetch");
    (mockF as ReturnType<typeof vi.fn>).mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddEditCredentialDialog mode="edit" initialName="GITHUB_TOKEN" token={null} onUnauthorized={noop} onSuccess={onSuccess} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^value/i), "newvalue");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockF).toHaveBeenCalledWith(
      expect.stringContaining("GITHUB_TOKEN"),
      expect.anything(),
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
