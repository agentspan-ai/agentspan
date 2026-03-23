import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BindingChips } from "../components/BindingChips";

const bindings = [
  { logical_key: "GH_TOKEN", store_name: "GITHUB_TOKEN" },
  { logical_key: "GITHUB_TOKEN", store_name: "GITHUB_TOKEN" },
];

describe("BindingChips", () => {
  it("renders empty-state text when no bindings", () => {
    render(<BindingChips bindings={[]} onDelete={vi.fn()} />);
    expect(screen.getByText(/no bindings/i)).toBeInTheDocument();
  });

  it("renders one chip per binding with logical_key → store_name", () => {
    render(<BindingChips bindings={bindings} onDelete={vi.fn()} />);
    expect(screen.getByText(/GH_TOKEN → GITHUB_TOKEN/)).toBeInTheDocument();
  });

  it("calls onDelete with logical_key when chip ✕ is clicked", async () => {
    const onDelete = vi.fn();
    const { container } = render(<BindingChips bindings={bindings} onDelete={onDelete} />);
    // MUI Chip renders the delete icon as an SVG with data-testid="CancelIcon" and aria-hidden="true"
    // Click the first CancelIcon SVG which belongs to the GH_TOKEN chip
    const deleteIcons = container.querySelectorAll('[data-testid="CancelIcon"]');
    await userEvent.click(deleteIcons[0]);
    expect(onDelete).toHaveBeenCalledWith("GH_TOKEN");
  });
});
