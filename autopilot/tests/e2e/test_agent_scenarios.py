"""E2e agent scenario tests — 15 tests that each create an agent, run it on the
real server, and verify the agent accomplished its goal.

NO mocks. Real server, real LLM, real tools.
Workflow completion is NOT success — the agent MUST accomplish the goal.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import Agent, AgentRuntime, EventType
from autopilot.loader import load_agent
from tests.e2e.conftest import assert_output_quality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMEOUT = 90  # seconds per agent run
_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")


def _create_agent_dir(tmp_path: Path, name: str, yaml_cfg: dict) -> Path:
    """Create agent directory with agent.yaml and workers/ dir."""
    agent_dir = tmp_path / "agents" / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "workers").mkdir()
    (agent_dir / "agent.yaml").write_text(yaml.dump(yaml_cfg))
    return agent_dir


def _run_agent(agent: Agent, prompt: str):
    """Run an agent on the real server, stream events, return (tool_calls, output).

    Raises pytest.fail on ERROR events or timeout.
    """
    with AgentRuntime() as runtime:
        handle = runtime.start(agent, prompt)
        print(f"  Execution: {handle.execution_id}")

        tool_calls: list[str] = []
        output = ""
        start = time.time()

        for event in handle.stream():
            if event.type == EventType.TOOL_CALL:
                name = event.tool_name or ""
                tool_calls.append(name)
                args = {k: v for k, v in (event.args or {}).items()
                        if not k.startswith("__")}
                print(f"  [{name}] {args}")

            elif event.type == EventType.TOOL_RESULT:
                result_str = str(event.result or "")
                print(f"    -> {len(result_str)} chars")

            elif event.type == EventType.DONE:
                out = event.output
                if isinstance(out, dict):
                    out = out.get("result", str(out))
                output = str(out)
                break

            elif event.type == EventType.ERROR:
                pytest.fail(f"Agent error: {event.content}")

            if time.time() - start > _TIMEOUT:
                handle.stop()
                pytest.fail(f"Agent timed out after {_TIMEOUT}s")

    return tool_calls, output


# ===========================================================================
# Category 1: Web Search Agents
# ===========================================================================


@pytest.mark.e2e
class TestWebSearchAgents:

    def test_search_and_summarize(self, tmp_path):
        """Agent searches for 'Python 3.13 new features' and summarizes."""
        agent_dir = _create_agent_dir(tmp_path, "search_summarizer", {
            "name": "search_summarizer",
            "model": _MODEL,
            "instructions": (
                "You are a web search agent. When given a query, use the web_search "
                "tool to search for information, then provide a detailed summary of "
                "what you find. Include specific facts and details from the search results."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent, "Search for 'Python 3.13 new features' and summarize what you find."
        )

        # Positive assertions
        assert any(t in ("web_search", "search_and_read") for t in tool_calls), \
            f"Expected web_search or search_and_read in {tool_calls}"
        assert_output_quality(output, min_length=100)
        assert "python" in output.lower(), \
            f"Output should mention Python but got: {output[:200]}"
        assert "3.13" in output or "3.12" in output or "python" in output.lower(), \
            f"Output should contain Python version info: {output[:200]}"

        # Negative assertions
        assert "error" not in output.lower()[:50], \
            f"Output starts with error: {output[:200]}"

        print(f"\n  SUCCESS: {len(tool_calls)} tool calls, {len(output)} chars output")

    def test_search_multiple_queries(self, tmp_path):
        """Agent searches for TWO topics and compares them."""
        agent_dir = _create_agent_dir(tmp_path, "multi_searcher", {
            "name": "multi_searcher",
            "model": _MODEL,
            "instructions": (
                "You are a comparison research agent. When asked to compare topics, "
                "you MUST use the web_search tool SEPARATELY for each topic (make "
                "two separate web_search calls with different queries). Then provide "
                "a comparison of both topics."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            "Compare the Rust programming language and the Go programming language. "
            "Search for each one SEPARATELY using web_search, then compare them."
        )

        # Count search calls (web_search or search_and_read)
        search_calls = [t for t in tool_calls
                        if t in ("web_search", "search_and_read")]
        assert len(search_calls) >= 2, \
            f"Expected at least 2 search calls, got {len(search_calls)}: {tool_calls}"

        assert_output_quality(output, min_length=150)
        output_lower = output.lower()
        assert "rust" in output_lower, f"Output should mention Rust: {output[:200]}"
        assert "go" in output_lower, f"Output should mention Go: {output[:200]}"

        print(f"\n  SUCCESS: {len(search_calls)} search calls, mentions both languages")

    def test_search_and_fetch_page(self, tmp_path):
        """Agent searches then fetches the top result for deeper reading."""
        agent_dir = _create_agent_dir(tmp_path, "deep_reader", {
            "name": "deep_reader",
            "model": _MODEL,
            "instructions": (
                "You are a deep research agent. When given a topic:\n"
                "1. First use web_search to find relevant pages.\n"
                "2. Then use fetch_page to read the FULL content of the most "
                "relevant result URL.\n"
                "3. Provide a detailed summary based on the full page content.\n"
                "You MUST call both web_search AND fetch_page."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            "Research the latest developments in quantum computing. First search "
            "the web, then fetch and read the most relevant page for details."
        )

        # Verify both tool types were called
        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        has_fetch = "fetch_page" in tool_calls or "search_and_read" in tool_calls
        assert has_search, f"Expected web_search in {tool_calls}"
        assert has_fetch, f"Expected fetch_page or search_and_read in {tool_calls}"

        # Deep fetch should produce longer output
        assert_output_quality(output, min_length=200)

        print(f"\n  SUCCESS: search + fetch, {len(output)} chars output")


# ===========================================================================
# Category 2: Local Filesystem Agents
# ===========================================================================


@pytest.mark.e2e
class TestLocalFsAgents:

    def test_read_and_summarize_files(self, tmp_path):
        """Agent reads 3 text files and produces a combined summary."""
        # Create data files
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "report_q1.txt").write_text(
            "Q1 2025 Revenue: $12.5 million. Growth rate: 15%. "
            "Key product: CloudSync platform. Customers: 340 enterprise clients."
        )
        (data_dir / "report_q2.txt").write_text(
            "Q2 2025 Revenue: $14.2 million. Growth rate: 13.6%. "
            "New product launch: DataBridge. Customers: 380 enterprise clients."
        )
        (data_dir / "report_q3.txt").write_text(
            "Q3 2025 Revenue: $16.8 million. Growth rate: 18.3%. "
            "Partnership with TechCorp announced. Customers: 425 enterprise clients."
        )

        agent_dir = _create_agent_dir(tmp_path, "file_summarizer", {
            "name": "file_summarizer",
            "model": _MODEL,
            "instructions": (
                "You are a file analysis agent. When asked to summarize files, "
                "use the read_file tool to read EACH file individually, then "
                "provide a combined summary that references data from ALL files. "
                "You MUST call read_file for each file path given to you."
            ),
            "tools": ["builtin:local_fs"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Read and summarize these three quarterly reports:\n"
            f"1. {data_dir / 'report_q1.txt'}\n"
            f"2. {data_dir / 'report_q2.txt'}\n"
            f"3. {data_dir / 'report_q3.txt'}\n"
            f"Provide a combined summary with key metrics from ALL three quarters."
        )

        # Verify read_file was called at least 3 times
        read_calls = [t for t in tool_calls if t == "read_file"]
        assert len(read_calls) >= 3, \
            f"Expected at least 3 read_file calls, got {len(read_calls)}: {tool_calls}"

        assert_output_quality(output, min_length=100)
        output_lower = output.lower()
        # Verify output references content from all 3 files
        assert "q1" in output_lower or "12.5" in output, \
            f"Output should mention Q1 data: {output[:300]}"
        assert "q2" in output_lower or "14.2" in output, \
            f"Output should mention Q2 data: {output[:300]}"
        assert "q3" in output_lower or "16.8" in output, \
            f"Output should mention Q3 data: {output[:300]}"

        print(f"\n  SUCCESS: {len(read_calls)} reads, all 3 quarters referenced")

    def test_find_and_read_pattern(self, tmp_path):
        """Agent uses find_files to locate .py files then reads them."""
        # Create mixed files
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(
            "def main():\n    print('Hello from main application')\n\nif __name__ == '__main__':\n    main()\n"
        )
        (project_dir / "utils.py").write_text(
            "def calculate_total(items):\n    return sum(item['price'] for item in items)\n"
        )
        (project_dir / "readme.txt").write_text("This is a text readme file.")
        (project_dir / "notes.md").write_text("# Project notes\nSome markdown notes.")

        agent_dir = _create_agent_dir(tmp_path, "file_finder", {
            "name": "file_finder",
            "model": _MODEL,
            "instructions": (
                "You are a code analysis agent. When asked to find and analyze files:\n"
                "1. First use find_files to locate files matching the pattern.\n"
                "2. find_files returns RELATIVE paths. To read them, you MUST "
                "prepend the original directory path to each result to form the "
                "absolute path. For example, if the directory is '/tmp/project' "
                "and find_files returns 'main.py', call read_file with "
                "'/tmp/project/main.py'.\n"
                "3. Provide a summary of what the code does.\n"
                "You MUST use find_files first, then read_file for each result."
            ),
            "tools": ["builtin:local_fs"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Find all Python files (*.py) in {project_dir} and analyze what "
            f"each one does. Use find_files with directory='{project_dir}' and "
            f"pattern='*.py' to locate them, then read_file to read each one. "
            f"Remember: find_files returns relative paths, so prepend "
            f"'{project_dir}/' to each file path when calling read_file."
        )

        assert "find_files" in tool_calls, \
            f"Expected find_files in {tool_calls}"
        assert "read_file" in tool_calls, \
            f"Expected read_file in {tool_calls}"
        assert_output_quality(output, min_length=80)

        # Output should reference the Python file content, not the .txt/.md files
        output_lower = output.lower()
        assert "main" in output_lower or "calculate" in output_lower, \
            f"Output should describe Python file content: {output[:300]}"

        print(f"\n  SUCCESS: find_files + read_file used, code content analyzed")

    def test_write_file_from_analysis(self, tmp_path):
        """Agent reads a data file, analyzes it, writes a summary file to disk."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        (data_dir / "sales.txt").write_text(
            "January: $45,000\nFebruary: $52,000\nMarch: $48,000\n"
            "April: $61,000\nMay: $58,000\nJune: $67,000\n"
            "Total H1: $331,000\nAverage monthly: $55,167\n"
        )

        summary_path = output_dir / "analysis.txt"

        agent_dir = _create_agent_dir(tmp_path, "file_writer", {
            "name": "file_writer",
            "model": _MODEL,
            "instructions": (
                "You are a data analysis agent. When asked to analyze a file and "
                "write a summary:\n"
                "1. Use read_file to read the input data.\n"
                "2. Analyze the data and identify trends.\n"
                "3. Use write_file to save your analysis to the specified output path.\n"
                "You MUST call both read_file AND write_file."
            ),
            "tools": ["builtin:local_fs"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Read the sales data from {data_dir / 'sales.txt'}, analyze the "
            f"monthly trends, and write your analysis to {summary_path}."
        )

        assert "read_file" in tool_calls, \
            f"Expected read_file in {tool_calls}"
        assert "write_file" in tool_calls, \
            f"Expected write_file in {tool_calls}"

        # Verify the file was actually written to disk
        assert summary_path.exists(), \
            f"Expected analysis file at {summary_path} but it doesn't exist"
        written_content = summary_path.read_text()
        assert len(written_content) > 20, \
            f"Written file is too short ({len(written_content)} chars)"

        assert_output_quality(output, min_length=50)
        print(f"\n  SUCCESS: read + write, file written ({len(written_content)} chars)")


# ===========================================================================
# Category 3: Document Reader Agents
# ===========================================================================


@pytest.mark.e2e
class TestDocReaderAgents:

    def test_read_plain_text_document(self, tmp_path):
        """Agent reads a structured .txt document and summarizes it."""
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        doc_path = doc_dir / "project_plan.txt"
        doc_path.write_text(
            "# Project Alpha - Implementation Plan\n\n"
            "## Phase 1: Foundation (Weeks 1-4)\n"
            "- Set up CI/CD pipeline\n"
            "- Design database schema\n"
            "- Implement authentication module\n\n"
            "## Phase 2: Core Features (Weeks 5-8)\n"
            "- Build REST API endpoints\n"
            "- Implement data processing pipeline\n"
            "- Create admin dashboard\n\n"
            "## Phase 3: Launch (Weeks 9-12)\n"
            "- Load testing and optimization\n"
            "- Security audit\n"
            "- Production deployment\n\n"
            "## Budget: $250,000\n"
            "## Team Size: 8 engineers\n"
        )

        agent_dir = _create_agent_dir(tmp_path, "doc_reader", {
            "name": "doc_reader",
            "model": _MODEL,
            "instructions": (
                "You are a document analysis agent. Use the read_document tool to "
                "read the given document, then provide a structured summary that "
                "captures the key sections, deliverables, and important numbers."
            ),
            "tools": ["builtin:doc_reader"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Read and summarize this project plan document: {doc_path}"
        )

        assert "read_document" in tool_calls, \
            f"Expected read_document in {tool_calls}"
        assert_output_quality(output, min_length=100)

        output_lower = output.lower()
        # Verify the summary reflects the document's structure
        assert "phase" in output_lower or "week" in output_lower, \
            f"Output should reference phases/weeks: {output[:300]}"
        assert "250,000" in output or "250000" in output or "budget" in output_lower, \
            f"Output should mention budget: {output[:300]}"

        print(f"\n  SUCCESS: document read and summarized with structure preserved")

    def test_read_csv_and_analyze(self, tmp_path):
        """Agent reads a CSV file with data and provides analysis."""
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        csv_path = doc_dir / "sales_data.csv"
        csv_path.write_text(
            "month,revenue,units_sold,region\n"
            "January,45000,120,North\n"
            "February,52000,145,North\n"
            "March,48000,130,South\n"
            "April,61000,170,East\n"
            "May,58000,155,West\n"
            "June,67000,185,North\n"
            "July,72000,200,East\n"
            "August,69000,190,South\n"
        )

        agent_dir = _create_agent_dir(tmp_path, "csv_analyzer", {
            "name": "csv_analyzer",
            "model": _MODEL,
            "instructions": (
                "You are a data analysis agent. Use the read_document tool to read "
                "the CSV file, then provide a detailed analysis including:\n"
                "- Total revenue\n"
                "- Best performing month\n"
                "- Revenue trends\n"
                "- Regional breakdown\n"
                "Include specific numbers from the data in your analysis."
            ),
            "tools": ["builtin:doc_reader"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Analyze this CSV sales data file: {csv_path}\n"
            f"Provide insights on revenue trends, best months, and regional performance."
        )

        assert "read_document" in tool_calls, \
            f"Expected read_document in {tool_calls}"
        assert_output_quality(output, min_length=100)

        # Verify output contains actual numbers from the CSV
        output_lower = output.lower()
        # Should mention at least some actual revenue figures or analysis
        has_numbers = any(num in output for num in
                         ["45000", "45,000", "72000", "72,000", "67000", "67,000"])
        has_analysis = any(word in output_lower for word in
                          ["revenue", "total", "highest", "best", "trend"])
        assert has_numbers or has_analysis, \
            f"Output should contain data analysis with numbers: {output[:300]}"

        print(f"\n  SUCCESS: CSV read and analyzed with specific data points")


# ===========================================================================
# Category 4: Multi-Tool Agents
# ===========================================================================


@pytest.mark.e2e
class TestMultiToolAgents:

    def test_search_then_save(self, tmp_path):
        """Agent searches the web then saves results to a local file."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        results_path = output_dir / "search_results.txt"

        agent_dir = _create_agent_dir(tmp_path, "search_saver", {
            "name": "search_saver",
            "model": _MODEL,
            "instructions": (
                "You are a research and filing agent. When given a topic:\n"
                "1. Use web_search to find information about the topic.\n"
                "2. Use write_file to save the search results and your summary "
                "to the specified file path.\n"
                "You MUST call both web_search AND write_file."
            ),
            "tools": ["builtin:web_search", "builtin:local_fs"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Search the web for 'benefits of TypeScript over JavaScript' and "
            f"save a summary of the results to {results_path}."
        )

        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        assert has_search, f"Expected web_search in {tool_calls}"
        assert "write_file" in tool_calls, \
            f"Expected write_file in {tool_calls}"

        # Verify the file exists on disk with meaningful content
        assert results_path.exists(), \
            f"Expected results file at {results_path} but it doesn't exist"
        written = results_path.read_text()
        assert len(written) > 50, \
            f"Written file too short ({len(written)} chars): {written[:100]}"

        assert_output_quality(output, min_length=50)
        print(f"\n  SUCCESS: searched + saved to file ({len(written)} chars)")

    def test_read_files_then_search(self, tmp_path):
        """Agent reads local files, identifies topics, then searches web."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "research_topic.txt").write_text(
            "Research Topic: Large Language Model Fine-tuning Techniques\n"
            "Focus areas: LoRA, QLoRA, and PEFT methods.\n"
            "Goal: Find recent papers and benchmarks from 2024-2025."
        )

        agent_dir = _create_agent_dir(tmp_path, "read_then_search", {
            "name": "read_then_search",
            "model": _MODEL,
            "instructions": (
                "You are a research assistant. When given a file path:\n"
                "1. First use read_file to read the research topic file.\n"
                "2. Then use web_search to find information about the topics "
                "mentioned in the file.\n"
                "3. Provide a combined report with findings.\n"
                "You MUST call both read_file AND web_search."
            ),
            "tools": ["builtin:local_fs", "builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Read the research topic from {data_dir / 'research_topic.txt'}, "
            f"then search the web for the topics described in it. Combine the "
            f"local context with web findings in your response."
        )

        assert "read_file" in tool_calls, \
            f"Expected read_file in {tool_calls}"
        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        assert has_search, f"Expected web_search in {tool_calls}"

        assert_output_quality(output, min_length=100)
        output_lower = output.lower()
        # Should mention topics from the local file AND web results
        assert any(term in output_lower for term in ["lora", "fine-tun", "peft"]), \
            f"Output should mention fine-tuning topics: {output[:300]}"

        print(f"\n  SUCCESS: read local file, searched web, combined results")

    def test_multi_step_research(self, tmp_path):
        """Agent does: search -> fetch_page -> write summary to file."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        report_path = output_dir / "research_report.txt"

        agent_dir = _create_agent_dir(tmp_path, "multi_step_researcher", {
            "name": "multi_step_researcher",
            "model": _MODEL,
            "instructions": (
                "You are a thorough research agent. Follow these steps exactly:\n"
                "1. Use web_search to find relevant pages about the topic.\n"
                "2. Use fetch_page to read the full content of the best result.\n"
                "3. Use write_file to save a comprehensive research report to the "
                "specified file path.\n"
                "You MUST call web_search, then fetch_page, then write_file — all three."
            ),
            "tools": ["builtin:web_search", "builtin:local_fs"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            f"Research 'WebAssembly use cases in 2025'. Search the web, fetch "
            f"the most relevant page for details, then write a research report "
            f"to {report_path}."
        )

        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        has_fetch = "fetch_page" in tool_calls or "search_and_read" in tool_calls
        assert has_search, f"Expected web_search in {tool_calls}"
        assert has_fetch, f"Expected fetch_page or search_and_read in {tool_calls}"
        assert "write_file" in tool_calls, \
            f"Expected write_file in {tool_calls}"

        # Verify file written to disk
        assert report_path.exists(), \
            f"Expected report at {report_path} but it doesn't exist"
        written = report_path.read_text()
        assert len(written) > 50, \
            f"Report file too short ({len(written)} chars)"

        assert_output_quality(output, min_length=50)
        print(f"\n  SUCCESS: search + fetch + write, report saved ({len(written)} chars)")


# ===========================================================================
# Category 5: Agent Behavior Patterns
# ===========================================================================


@pytest.mark.e2e
class TestAgentBehaviorPatterns:

    def test_agent_follows_instructions(self, tmp_path):
        """Agent with specific formatting instructions produces bullet points."""
        agent_dir = _create_agent_dir(tmp_path, "bullet_pointer", {
            "name": "bullet_pointer",
            "model": _MODEL,
            "instructions": (
                "You are a concise summary agent. You MUST follow these rules EXACTLY:\n"
                "1. ONLY respond with bullet points using '- ' prefix.\n"
                "2. Maximum 5 bullet points.\n"
                "3. Each bullet must be one sentence.\n"
                "4. Do NOT include any introduction, conclusion, or extra text.\n"
                "5. Start your response directly with '- '.\n"
                "Search the web for information first, then format as bullet points."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            "What are the key features of the Rust programming language?"
        )

        assert_output_quality(output, min_length=50)

        # Verify bullet point formatting
        lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
        bullet_lines = [l for l in lines if l.startswith("- ") or l.startswith("* ")]
        assert len(bullet_lines) >= 2, \
            f"Expected at least 2 bullet points, got {len(bullet_lines)} in:\n{output}"
        assert len(bullet_lines) <= 7, \
            f"Expected max ~5 bullet points, got {len(bullet_lines)} in:\n{output}"

        print(f"\n  SUCCESS: {len(bullet_lines)} bullet points, format followed")

    def test_agent_handles_no_results(self, tmp_path):
        """Agent searches for gibberish and handles gracefully."""
        agent_dir = _create_agent_dir(tmp_path, "graceful_handler", {
            "name": "graceful_handler",
            "model": _MODEL,
            "instructions": (
                "You are a web search agent. Search for exactly what the user asks. "
                "If search results are empty or irrelevant, honestly say so. "
                "Do NOT make up information. Do NOT hallucinate facts. "
                "If you find nothing useful, explain that the search returned "
                "limited or no relevant results."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        tool_calls, output = _run_agent(
            agent,
            "Search for 'xyzzy99999qqqq zzzzfake nonsense term aaaa7777' and "
            "tell me what you find."
        )

        # Agent should still attempt the search (not skip it)
        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        assert has_search, f"Expected a search attempt in {tool_calls}"

        # Agent should produce SOME output (not crash)
        assert output, "Agent produced no output for gibberish query"
        assert len(output) > 20, f"Output too short: {output}"

        # Agent should NOT hallucinate detailed factual content about gibberish
        # (it should indicate limited/no results, not invent a topic)
        output_lower = output.lower()
        hallucination_signals = [
            "xyzzy99999qqqq is a",
            "xyzzy99999qqqq was founded",
            "xyzzy99999qqqq is known for",
        ]
        for signal in hallucination_signals:
            assert signal not in output_lower, \
                f"Agent appears to be hallucinating about gibberish: {output[:300]}"

        print(f"\n  SUCCESS: Agent handled gibberish gracefully, no hallucination")

    def test_agent_with_error_handling_config(self, tmp_path):
        """Agent with error_handling YAML config loads and runs correctly."""
        agent_dir = _create_agent_dir(tmp_path, "error_handler", {
            "name": "error_handler",
            "model": _MODEL,
            "instructions": (
                "You are a simple search agent. Search the web for what the user "
                "asks and provide a summary."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {
                "max_retries": 3,
                "backoff": "exponential",
                "on_failure": "pause_and_notify",
            },
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"

        # Verify error_handling is in metadata
        assert agent.metadata is not None, "Agent metadata should not be None"
        assert "error_handling" in agent.metadata, \
            f"error_handling not in metadata: {agent.metadata}"
        eh = agent.metadata["error_handling"]
        assert eh["max_retries"] == 3, f"max_retries should be 3, got {eh['max_retries']}"
        assert eh["backoff"] == "exponential", f"backoff should be exponential"
        assert eh["on_failure"] == "pause_and_notify"

        # Also verify the agent runs correctly
        tool_calls, output = _run_agent(
            agent,
            "Search for 'Python asyncio tutorial' and give me a brief summary."
        )

        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        assert has_search, f"Expected search call in {tool_calls}"
        assert_output_quality(output, min_length=50)

        print(f"\n  SUCCESS: error_handling config loaded correctly, agent ran fine")

    def test_agent_with_multiple_tools_uses_right_one(self, tmp_path):
        """Agent with web_search + local_fs + doc_reader uses web_search when
        told to search the web, and does NOT use local_fs."""
        agent_dir = _create_agent_dir(tmp_path, "tool_selector", {
            "name": "tool_selector",
            "model": _MODEL,
            "instructions": (
                "You are a versatile agent with access to web search, local "
                "filesystem, and document reader tools. Use the appropriate tool "
                "based on what the user asks. If the user asks to search the web, "
                "use web_search. If the user asks to read local files, use "
                "read_file. Choose the right tool for the task."
            ),
            "tools": ["builtin:web_search", "builtin:local_fs", "builtin:doc_reader"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential",
                               "on_failure": "pause_and_notify"},
        })

        agent = load_agent(agent_dir)
        assert agent.tools, "Agent has no tools"
        tool_names = [t._tool_def.name for t in agent.tools]
        # Should have tools from all three integrations
        assert "web_search" in tool_names, f"Missing web_search in {tool_names}"
        assert "read_file" in tool_names, f"Missing read_file in {tool_names}"
        assert "read_document" in tool_names, f"Missing read_document in {tool_names}"

        tool_calls, output = _run_agent(
            agent,
            "Search the web for 'Kubernetes vs Docker Swarm comparison 2025' "
            "and summarize the key differences."
        )

        # web_search should be called
        has_search = any(t in ("web_search", "search_and_read") for t in tool_calls)
        assert has_search, f"Expected web_search in {tool_calls}"

        # local_fs tools should NOT be called (no files to read)
        local_fs_tools = {"read_file", "write_file", "list_dir", "find_files",
                          "search_in_files"}
        used_local = local_fs_tools.intersection(set(tool_calls))
        assert not used_local, \
            f"Agent should NOT have used local_fs tools, but called: {used_local}"

        # doc_reader should NOT be called
        assert "read_document" not in tool_calls, \
            f"Agent should NOT have used read_document for a web search task"

        assert_output_quality(output, min_length=100)
        print(f"\n  SUCCESS: Used web_search, correctly avoided local_fs/doc_reader")
