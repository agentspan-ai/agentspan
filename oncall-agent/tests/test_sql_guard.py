import pytest

from oncall_agent.sql_guard import NotReadOnlySQLError, ensure_select

VALID = [
    "SELECT * FROM workflow LIMIT 10",
    "select count(*) from task_in_progress",
    "SELECT * FROM workflow WHERE status='RUNNING';",  # trailing semicolon ok
    "WITH t AS (SELECT id FROM workflow) SELECT * FROM t",
    "EXPLAIN SELECT * FROM workflow",
    "SHOW server_version",
    "  SELECT 1 /* inline comment */ ",
]

INVALID = [
    "",
    "   ",
    "-- just a comment",
    "DELETE FROM workflow",
    "UPDATE workflow SET status='X'",
    "INSERT INTO workflow VALUES (1)",
    "DROP TABLE workflow",
    "TRUNCATE workflow",
    "GRANT ALL ON workflow TO public",
    "SET search_path TO public",
    "SELECT 1; DROP TABLE workflow",                  # two statements
    "SELECT 1; SELECT 2",                              # two selects
    "SELECT 1 -- harmless\n; DROP TABLE x",            # comment-hidden 2nd statement
    "WITH x AS (DELETE FROM workflow RETURNING *) SELECT * FROM x",  # mutation in CTE
]


@pytest.mark.parametrize("q", VALID)
def test_valid_select_passes(q):
    assert ensure_select(q)


@pytest.mark.parametrize("q", INVALID)
def test_mutating_or_multi_statement_rejected(q):
    with pytest.raises(NotReadOnlySQLError):
        ensure_select(q)
