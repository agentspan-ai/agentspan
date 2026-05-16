// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 17 — SQL Agent
 *
 * <p>Java port of <code>sdk/python/examples/langchain/17_sql_agent.py</code>.
 *
 * <p>Demonstrates schema introspection, query validation, and SELECT execution
 * against a simulated in-memory employees table. Python uses sqlite3
 * in-memory; the Java port uses a HashMap-backed mock with a tiny SQL
 * parser to keep the same tool names and signatures without adding a
 * database dependency.
 */
public class ExampleLc4j17SqlAgent {

    // ── Simulated in-memory database ─────────────────────────────────────────

    /** Single seed table: employees(id, name, department, salary, hire_year). */
    static final List<Map<String, Object>> EMPLOYEES = new ArrayList<>();
    /** Column name -> type, in declaration order. */
    static final Map<String, String> EMPLOYEES_SCHEMA = new LinkedHashMap<>();

    static {
        EMPLOYEES_SCHEMA.put("id", "INTEGER");
        EMPLOYEES_SCHEMA.put("name", "TEXT");
        EMPLOYEES_SCHEMA.put("department", "TEXT");
        EMPLOYEES_SCHEMA.put("salary", "REAL");
        EMPLOYEES_SCHEMA.put("hire_year", "INTEGER");

        EMPLOYEES.add(row(1, "Alice Chen", "Engineering", 95000.0, 2020));
        EMPLOYEES.add(row(2, "Bob Martinez", "Marketing", 72000.0, 2019));
        EMPLOYEES.add(row(3, "Carol Williams", "Engineering", 105000.0, 2018));
        EMPLOYEES.add(row(4, "Dave Johnson", "HR", 68000.0, 2021));
        EMPLOYEES.add(row(5, "Eve Davis", "Engineering", 88000.0, 2022));
        EMPLOYEES.add(row(6, "Frank Lee", "Marketing", 79000.0, 2020));
        EMPLOYEES.add(row(7, "Grace Kim", "HR", 71000.0, 2019));
        EMPLOYEES.add(row(8, "Henry Brown", "Engineering", 112000.0, 2017));
    }

    private static Map<String, Object> row(int id, String name, String dept, double salary, int hireYear) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("id", id);
        r.put("name", name);
        r.put("department", dept);
        r.put("salary", salary);
        r.put("hire_year", hireYear);
        return r;
    }

    // ── LangChain4j tools ─────────────────────────────────────────────────────

    public static class SqlTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "get_schema",
            value = "Return the database schema: table names and column definitions."
        )
        public String getSchema() {
            StringBuilder cols = new StringBuilder();
            boolean first = true;
            for (Map.Entry<String, String> e : EMPLOYEES_SCHEMA.entrySet()) {
                if (!first) cols.append(", ");
                cols.append(e.getKey()).append(" ").append(e.getValue());
                first = false;
            }
            return "Table 'employees': " + cols;
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "execute_query",
            value = "Execute a SELECT SQL query and return the results as formatted text. "
                + "Only SELECT queries are allowed for safety."
        )
        public String executeQuery(@dev.langchain4j.agent.tool.P("sql") String sql) {
            if (sql == null) return "Error: Only SELECT queries are permitted.";
            String stripped = sql.trim().toUpperCase(Locale.ROOT);
            if (!stripped.startsWith("SELECT")) {
                return "Error: Only SELECT queries are permitted.";
            }
            try {
                QueryResult qr = runSelect(sql);
                if (qr.rows.isEmpty()) return "Query returned no results.";

                List<String> lines = new ArrayList<>();
                String header = String.join(" | ", qr.columns);
                lines.add(header);
                StringBuilder sep = new StringBuilder();
                for (int i = 0; i < header.length(); i++) sep.append("-");
                lines.add(sep.toString());
                for (List<Object> row : qr.rows) {
                    List<String> cells = new ArrayList<>();
                    for (Object v : row) cells.add(String.valueOf(v));
                    lines.add(String.join(" | ", cells));
                }
                return String.join("\n", lines);
            } catch (Exception e) {
                return "SQL error: " + e.getMessage();
            }
        }
    }

    // ── Minimal SQL evaluator for the simulated table ───────────────────────

    static class QueryResult {
        final List<String> columns;
        final List<List<Object>> rows;

        QueryResult(List<String> columns, List<List<Object>> rows) {
            this.columns = columns;
            this.rows = rows;
        }
    }

    /**
     * Tiny SELECT evaluator supporting the shapes the LLM is likely to emit:
     *   SELECT *|col,col FROM employees
     *   [WHERE col OP value [AND ...]]
     *   [GROUP BY col]
     *   [ORDER BY col [ASC|DESC]]
     *   [LIMIT n]
     * Aggregates supported in projection: COUNT(*), AVG(col), SUM(col), MIN(col), MAX(col).
     */
    static QueryResult runSelect(String sql) {
        String s = sql.trim();
        if (s.endsWith(";")) s = s.substring(0, s.length() - 1).trim();
        String upper = s.toUpperCase(Locale.ROOT);

        int fromIdx = upper.indexOf(" FROM ");
        if (fromIdx < 0) throw new RuntimeException("missing FROM clause");
        String projection = s.substring("SELECT".length(), fromIdx).trim();

        int whereIdx = upper.indexOf(" WHERE ", fromIdx);
        int groupIdx = upper.indexOf(" GROUP BY ", fromIdx);
        int orderIdx = upper.indexOf(" ORDER BY ", fromIdx);
        int limitIdx = upper.indexOf(" LIMIT ", fromIdx);

        int tableEnd = firstPositive(s.length(), whereIdx, groupIdx, orderIdx, limitIdx);
        String table = s.substring(fromIdx + " FROM ".length(), tableEnd).trim();
        if (!"employees".equalsIgnoreCase(table)) {
            throw new RuntimeException("unknown table: " + table);
        }

        // WHERE
        String whereClause = null;
        if (whereIdx >= 0) {
            int end = firstPositive(s.length(), groupIdx, orderIdx, limitIdx);
            whereClause = s.substring(whereIdx + " WHERE ".length(), end).trim();
        }

        // GROUP BY
        String groupBy = null;
        if (groupIdx >= 0) {
            int end = firstPositive(s.length(), orderIdx, limitIdx);
            groupBy = s.substring(groupIdx + " GROUP BY ".length(), end).trim();
        }

        // ORDER BY
        String orderBy = null;
        boolean orderDesc = false;
        if (orderIdx >= 0) {
            int end = firstPositive(s.length(), limitIdx);
            String ob = s.substring(orderIdx + " ORDER BY ".length(), end).trim();
            String[] parts = ob.split("\\s+");
            orderBy = parts[0];
            if (parts.length > 1 && parts[1].equalsIgnoreCase("DESC")) orderDesc = true;
        }

        // LIMIT
        Integer limit = null;
        if (limitIdx >= 0) {
            String l = s.substring(limitIdx + " LIMIT ".length()).trim();
            limit = Integer.parseInt(l);
        }

        // Filter
        List<Map<String, Object>> filtered = new ArrayList<>();
        for (Map<String, Object> r : EMPLOYEES) {
            if (whereClause == null || evalWhere(whereClause, r)) {
                filtered.add(r);
            }
        }

        // Projection / aggregation
        List<String> projItems = splitTopLevel(projection);
        boolean hasAggregate = false;
        for (String p : projItems) {
            String u = p.trim().toUpperCase(Locale.ROOT);
            if (u.startsWith("COUNT(") || u.startsWith("AVG(") || u.startsWith("SUM(")
                || u.startsWith("MIN(") || u.startsWith("MAX(")) {
                hasAggregate = true;
                break;
            }
        }

        List<String> columns = new ArrayList<>();
        List<List<Object>> rows = new ArrayList<>();

        if (groupBy != null || hasAggregate) {
            // Group rows
            Map<Object, List<Map<String, Object>>> groups = new LinkedHashMap<>();
            if (groupBy != null) {
                for (Map<String, Object> r : filtered) {
                    Object key = r.get(groupBy);
                    groups.computeIfAbsent(key, k -> new ArrayList<>()).add(r);
                }
            } else {
                groups.put(null, filtered);
            }

            for (String p : projItems) {
                columns.add(stripAlias(p.trim()));
            }

            for (Map.Entry<Object, List<Map<String, Object>>> e : groups.entrySet()) {
                List<Object> outRow = new ArrayList<>();
                for (String p : projItems) {
                    outRow.add(evalProjection(p.trim(), e.getValue(), e.getKey(), groupBy));
                }
                rows.add(outRow);
            }
        } else {
            // Plain projection
            if (projItems.size() == 1 && projItems.get(0).trim().equals("*")) {
                columns.addAll(EMPLOYEES_SCHEMA.keySet());
            } else {
                for (String p : projItems) columns.add(stripAlias(p.trim()));
            }
            for (Map<String, Object> r : filtered) {
                List<Object> outRow = new ArrayList<>();
                for (String c : columns) outRow.add(r.get(c));
                rows.add(outRow);
            }
        }

        // ORDER BY (after aggregation so aggregated columns can be ordered)
        if (orderBy != null) {
            final String ob = stripAlias(orderBy.trim());
            final boolean desc = orderDesc;
            int idx = columns.indexOf(ob);
            if (idx >= 0) {
                rows.sort((a, b) -> compareValues(a.get(idx), b.get(idx), desc));
            }
        }

        // LIMIT
        if (limit != null && rows.size() > limit) {
            rows = new ArrayList<>(rows.subList(0, limit));
        }

        return new QueryResult(columns, rows);
    }

    private static int firstPositive(int defaultValue, int... idxs) {
        int min = defaultValue;
        for (int i : idxs) {
            if (i >= 0 && i < min) min = i;
        }
        return min;
    }

    private static List<String> splitTopLevel(String csv) {
        // Split a comma list while respecting parentheses
        List<String> out = new ArrayList<>();
        int depth = 0;
        StringBuilder cur = new StringBuilder();
        for (int i = 0; i < csv.length(); i++) {
            char c = csv.charAt(i);
            if (c == '(') depth++;
            else if (c == ')') depth--;
            if (c == ',' && depth == 0) {
                out.add(cur.toString());
                cur.setLength(0);
            } else {
                cur.append(c);
            }
        }
        if (cur.length() > 0) out.add(cur.toString());
        return out;
    }

    private static String stripAlias(String expr) {
        // "AVG(salary) AS avg_sal" -> "avg_sal"; "salary" stays "salary".
        String upper = expr.toUpperCase(Locale.ROOT);
        int asIdx = upper.indexOf(" AS ");
        if (asIdx > 0) {
            return expr.substring(asIdx + 4).trim();
        }
        return expr.trim();
    }

    private static Object evalProjection(
            String expr,
            List<Map<String, Object>> rows,
            Object groupKey,
            String groupCol) {
        String base = expr;
        String upper = base.toUpperCase(Locale.ROOT);
        int asIdx = upper.indexOf(" AS ");
        if (asIdx > 0) base = base.substring(0, asIdx).trim();

        String u = base.toUpperCase(Locale.ROOT);
        if (u.startsWith("COUNT(")) {
            return rows.size();
        }
        if (u.startsWith("AVG(") || u.startsWith("SUM(") || u.startsWith("MIN(") || u.startsWith("MAX(")) {
            int open = base.indexOf('(');
            int close = base.lastIndexOf(')');
            String col = base.substring(open + 1, close).trim();
            double sum = 0;
            double min = Double.POSITIVE_INFINITY;
            double max = Double.NEGATIVE_INFINITY;
            int n = 0;
            for (Map<String, Object> r : rows) {
                Object v = r.get(col);
                if (v instanceof Number) {
                    double d = ((Number) v).doubleValue();
                    sum += d;
                    if (d < min) min = d;
                    if (d > max) max = d;
                    n++;
                }
            }
            if (n == 0) return 0;
            if (u.startsWith("AVG(")) return sum / n;
            if (u.startsWith("SUM(")) return sum;
            if (u.startsWith("MIN(")) return min;
            return max;
        }
        // Plain column reference — yield group key for GROUP BY column, else first row's value.
        if (groupCol != null && base.equalsIgnoreCase(groupCol)) return groupKey;
        return rows.isEmpty() ? null : rows.get(0).get(base);
    }

    private static boolean evalWhere(String clause, Map<String, Object> r) {
        // Supports simple AND-joined conditions: col OP value
        String[] parts = clause.split("(?i)\\s+AND\\s+");
        for (String p : parts) {
            if (!evalCondition(p.trim(), r)) return false;
        }
        return true;
    }

    private static boolean evalCondition(String cond, Map<String, Object> r) {
        String[] ops = {">=", "<=", "!=", "<>", "=", ">", "<"};
        for (String op : ops) {
            int idx = cond.indexOf(op);
            if (idx > 0) {
                String col = cond.substring(0, idx).trim();
                String valStr = cond.substring(idx + op.length()).trim();
                if (valStr.startsWith("'") && valStr.endsWith("'")) {
                    valStr = valStr.substring(1, valStr.length() - 1);
                } else if (valStr.startsWith("\"") && valStr.endsWith("\"")) {
                    valStr = valStr.substring(1, valStr.length() - 1);
                }
                Object cell = r.get(col);
                return compareForOp(cell, valStr, op);
            }
        }
        return true;
    }

    private static boolean compareForOp(Object cell, String valStr, String op) {
        if (cell instanceof Number) {
            double a = ((Number) cell).doubleValue();
            double b;
            try { b = Double.parseDouble(valStr); } catch (NumberFormatException e) { return false; }
            switch (op) {
                case "=": return a == b;
                case "!=": case "<>": return a != b;
                case ">": return a > b;
                case "<": return a < b;
                case ">=": return a >= b;
                case "<=": return a <= b;
            }
        }
        String a = String.valueOf(cell);
        switch (op) {
            case "=": return a.equals(valStr);
            case "!=": case "<>": return !a.equals(valStr);
            default: return false;
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static int compareValues(Object a, Object b, boolean desc) {
        int cmp;
        if (a instanceof Number && b instanceof Number) {
            cmp = Double.compare(((Number) a).doubleValue(), ((Number) b).doubleValue());
        } else if (a instanceof Comparable && b instanceof Comparable) {
            cmp = ((Comparable) a).compareTo(b);
        } else {
            cmp = String.valueOf(a).compareTo(String.valueOf(b));
        }
        return desc ? -cmp : cmp;
    }

    // ── Main ─────────────────────────────────────────────────────────────────

    public static void main(String[] args) {
        // Reference Arrays import so the simulated table init compiles cleanly.
        @SuppressWarnings("unused")
        List<String> _unused = Arrays.asList("ref");

        Agent agent = LangChain4jAgent.from(
            "sql_agent",
            Settings.LLM_MODEL,
            "You are a SQL assistant. Always inspect the schema first, then write and execute a SELECT query. "
                + "Translate natural language questions into correct SQL.",
            new SqlTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Which department has the highest average salary? Show me the top 3 earners in Engineering."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
