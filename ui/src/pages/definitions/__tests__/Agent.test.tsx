import { render } from "@testing-library/react";
import { createContext } from "react";
import { QueryClient, QueryClientProvider } from "react-query";
import { MemoryRouter } from "react-router";
import AgentDefinitions from "../Agent";

vi.mock("utils/query", () => ({
  useWorkflowDefs: () => ({
    data: [
      {
        name: "test_agent",
        version: 1,
        createTime: 0,
        tags: [],
        inputParameters: [],
      },
    ],
    isFetching: false,
    refetch: vi.fn(),
  }),
  useActionWithPath: () => ({ mutate: vi.fn() }),
}));

vi.mock("shared/auth", () => ({
  useAuth: () => ({ isTrialExpired: false }),
}));

vi.mock("components/v1/layout/MessageContext", () => ({
  MessageContext: createContext({ setMessage: () => {} }),
}));

vi.mock("utils/hooks/usePushHistory", () => ({
  usePushHistory: () => vi.fn(),
}));

vi.mock("utils/hooks/useCustomPagination", () => ({
  default: () => [
    { filterParam: "", pageParam: "1", searchParam: "" },
    {
      setFilterParam: vi.fn(),
      setSearchParam: vi.fn(),
      handlePageChange: vi.fn(),
    },
  ],
}));

vi.mock("pages/runWorkflow/runWorkflowUtils", () => ({
  removeDeletedWorkflow: vi.fn(),
}));

vi.mock("utils/workflow", () => ({
  getUniqueWorkflows: (data: any[]) => data,
}));

// Render DataTable minimally: invoke the `actions` column renderer with row data
vi.mock("components", () => ({
  Button: ({ children, ...p }: any) => <button {...p}>{children}</button>,
  DataTable: ({ columns, data }: any) => {
    const actionsCol = columns.find((c: any) => c.id === "actions");
    return (
      <div>
        {data.map((row: any) => (
          <div key={row.name}>{actionsCol.renderer(row.name, row)}</div>
        ))}
      </div>
    );
  },
  IconButton: ({ children, id, ...p }: any) => (
    <button id={id} {...p}>
      {children}
    </button>
  ),
  NavLink: ({ children }: any) => <a>{children}</a>,
  Paper: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("components/Header", () => ({
  default: () => null,
}));
vi.mock("components/NoDataComponent", () => ({
  default: () => null,
}));
vi.mock("components/SnackbarMessage", () => ({
  SnackbarMessage: () => null,
}));
vi.mock("components/ConfirmChoiceDialog", () => ({
  default: () => null,
}));
vi.mock("components/tags/AddTagDialog", () => ({
  default: () => null,
}));
vi.mock("components/v1/TagList", () => ({
  default: () => null,
}));
vi.mock("components/v1/icons/PlayIcon", () => ({
  default: () => null,
}));
vi.mock("shared/SectionHeader", () => ({
  default: ({ title }: any) => <h1>{title}</h1>,
}));
vi.mock("shared/SectionHeaderActions", () => ({
  default: () => null,
}));
vi.mock("shared/SectionContainer", () => ({
  default: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("./dialog/CloneAgentDialog", () => ({
  default: () => null,
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("AgentDefinitions row actions", () => {
  it("does not render a Run action button for the row", () => {
    render(<AgentDefinitions />, { wrapper });
    expect(
      document.getElementById("run-test_agent-btn"),
    ).not.toBeInTheDocument();
  });

  it("does not render an Add/Edit Tags action button for the row", () => {
    render(<AgentDefinitions />, { wrapper });
    expect(
      document.getElementById("add-tags-test_agent-btn"),
    ).not.toBeInTheDocument();
  });

  it("still renders the Delete action button for the row", () => {
    render(<AgentDefinitions />, { wrapper });
    expect(
      document.getElementById("delete-test_agent-btn"),
    ).toBeInTheDocument();
  });
});
