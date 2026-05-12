// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example Lc4j 25 — Advanced Orchestration
 *
 * <p>Java port of <code>sdk/python/examples/langchain/25_advanced_orchestration.py</code>.
 *
 * <p>Demonstrates a multi-domain toolset (company profiles, market trends,
 * business metric formulas, and report-section formatting) wired together
 * with a planner-style system prompt.
 */
public class ExampleLc4j25AdvancedOrchestration {

    static class CompanyInfo {
        final String name;
        final int founded;
        final String ceo;
        final String focus;
        final String valuation;

        CompanyInfo(String name, int founded, String ceo, String focus, String valuation) {
            this.name = name;
            this.founded = founded;
            this.ceo = ceo;
            this.focus = focus;
            this.valuation = valuation;
        }
    }

    static final Map<String, CompanyInfo> COMPANIES = new LinkedHashMap<>();
    static final Map<String, String> SECTOR_TRENDS = new LinkedHashMap<>();

    static {
        COMPANIES.put("openai", new CompanyInfo(
            "OpenAI", 2015, "Sam Altman", "AGI research and deployment", "$157B (2025)"));
        COMPANIES.put("anthropic", new CompanyInfo(
            "Anthropic", 2021, "Dario Amodei", "AI safety research", "$61B (2025)"));
        COMPANIES.put("google", new CompanyInfo(
            "Alphabet/Google", 1998, "Sundar Pichai", "Search, cloud, AI", "$2.1T (2025)"));
        COMPANIES.put("microsoft", new CompanyInfo(
            "Microsoft", 1975, "Satya Nadella", "Cloud, AI, productivity", "$3.1T (2025)"));

        SECTOR_TRENDS.put("ai",
            "Key trends: LLM commoditization, multimodal AI, agentic systems, "
                + "edge AI deployment. Growth: 37% CAGR through 2030.");
        SECTOR_TRENDS.put("cloud computing",
            "Key trends: hybrid cloud, serverless, FinOps cost optimization, "
                + "AI/ML infrastructure. Market: $670B by 2025.");
        SECTOR_TRENDS.put("fintech",
            "Key trends: embedded finance, BNPL regulation, CBDCs, AI fraud detection. "
                + "Investment: $50B in 2024.");
        SECTOR_TRENDS.put("cybersecurity",
            "Key trends: zero-trust architecture, AI-driven threat detection, "
                + "ransomware surge. Market: $300B by 2026.");
        SECTOR_TRENDS.put("healthcare",
            "Key trends: AI diagnostics, telemedicine growth, personalized medicine, "
                + "EHR integration. Market: $500B by 2026.");
    }

    public static class OrchestrationTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "get_company_info",
            value = "Retrieve company profile information."
        )
        public String getCompanyInfo(@dev.langchain4j.agent.tool.P("company") String company) {
            String key = company == null ? "" : company.toLowerCase(Locale.ROOT)
                .replace(".", "").replace(",", "");
            for (Map.Entry<String, CompanyInfo> e : COMPANIES.entrySet()) {
                if (key.contains(e.getKey()) || e.getKey().contains(key)) {
                    return companyJson(e.getValue());
                }
            }
            return "No company profile found for '" + company + "'.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_market_trends",
            value = "Retrieve current market trends for a sector."
        )
        public String getMarketTrends(@dev.langchain4j.agent.tool.P("sector") String sector) {
            String lower = sector == null ? "" : sector.toLowerCase(Locale.ROOT);
            for (Map.Entry<String, String> e : SECTOR_TRENDS.entrySet()) {
                if (lower.contains(e.getKey())) return e.getValue();
            }
            return "No trend data for sector '" + sector + "'.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "calculate_metric",
            value = "Compute a business metric using a named formula and input values. "
                + "values is a JSON string with the required input values."
        )
        public String calculateMetric(
                @dev.langchain4j.agent.tool.P("formula") String formula,
                @dev.langchain4j.agent.tool.P("values") String values) {
            Map<String, Double> data;
            try {
                data = parseSimpleJsonNumbers(values == null ? "" : values);
            } catch (Exception e) {
                return "Error: values must be a valid JSON string.";
            }
            String formulaLower = formula == null ? "" : formula.toLowerCase(Locale.ROOT);
            try {
                if (formulaLower.contains("roi")) {
                    double gain = data.getOrDefault("gain", 0.0);
                    double cost = data.getOrDefault("cost", 1.0);
                    if (cost == 0.0) cost = 1.0;
                    double roi = ((gain - cost) / cost) * 100.0;
                    return "ROI = " + String.format(Locale.ROOT, "%.1f", roi) + "%";
                }
                if (formulaLower.contains("cagr")) {
                    double start = data.getOrDefault("start", 1.0);
                    double end = data.getOrDefault("end", 1.0);
                    double years = data.getOrDefault("years", 1.0);
                    if (start == 0.0) start = 1.0;
                    if (years == 0.0) years = 1.0;
                    double cagr = (Math.pow(end / start, 1.0 / years) - 1.0) * 100.0;
                    return "CAGR = " + String.format(Locale.ROOT, "%.1f", cagr) + "%";
                }
                if (formulaLower.contains("market_share")) {
                    double companyVal = data.getOrDefault("company", 0.0);
                    double total = data.getOrDefault("total", 1.0);
                    if (total == 0.0) total = 1.0;
                    double share = (companyVal / total) * 100.0;
                    return "Market share = " + String.format(Locale.ROOT, "%.1f", share) + "%";
                }
                return "Unknown formula '" + formula + "'. Supported: ROI, CAGR, market_share.";
            } catch (Exception e) {
                return "Calculation error: " + e.getMessage();
            }
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "generate_report_section",
            value = "Format content as a professional report section."
        )
        public String generateReportSection(
                @dev.langchain4j.agent.tool.P("section_type") String sectionType,
                @dev.langchain4j.agent.tool.P("content") String content) {
            String now = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE);
            String key = sectionType == null ? "" : sectionType.toLowerCase(Locale.ROOT).replace(" ", "_");
            switch (key) {
                case "executive_summary":
                    return "## Executive Summary\n*Report Date: " + now + "*\n\n" + content;
                case "findings":
                    return "## Key Findings\n\n" + content;
                case "recommendations":
                    return "## Recommendations\n\n" + content;
                default:
                    String title = sectionType == null || sectionType.isEmpty()
                        ? "Section"
                        : Character.toUpperCase(sectionType.charAt(0))
                            + sectionType.substring(1);
                    return "## " + title + "\n\n" + content;
            }
        }
    }

    private static String companyJson(CompanyInfo c) {
        // Mirror Python's json.dumps(v, indent=2) shape.
        StringBuilder sb = new StringBuilder("{\n");
        sb.append("  \"name\": \"").append(escape(c.name)).append("\",\n");
        sb.append("  \"founded\": ").append(c.founded).append(",\n");
        sb.append("  \"ceo\": \"").append(escape(c.ceo)).append("\",\n");
        sb.append("  \"focus\": \"").append(escape(c.focus)).append("\",\n");
        sb.append("  \"valuation\": \"").append(escape(c.valuation)).append("\"\n");
        sb.append("}");
        return sb.toString();
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    /**
     * Minimal JSON-numbers parser sufficient for the LLM-emitted
     * {"gain": 1000, "cost": 800} style payloads.
     * Throws if the input is structurally invalid.
     */
    private static Map<String, Double> parseSimpleJsonNumbers(String json) {
        Map<String, Double> out = new LinkedHashMap<>();
        if (json == null) throw new RuntimeException("null");
        String s = json.trim();
        if (!s.startsWith("{") || !s.endsWith("}")) {
            throw new RuntimeException("not a JSON object");
        }
        s = s.substring(1, s.length() - 1).trim();
        if (s.isEmpty()) return out;

        // Accept scientific notation (e.g. 1.8e12, -3.4E-2) and quoted numeric
        // strings ("1800") so the parser tolerates whatever shape the LLM
        // emits, matching Python's json.loads(...) flexibility.
        Pattern p = Pattern.compile(
            "\"([^\"]+)\"\\s*:\\s*(?:\"(-?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?)\"|(-?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?))"
        );
        Matcher m = p.matcher(s);
        while (m.find()) {
            String num = m.group(2) != null ? m.group(2) : m.group(3);
            out.put(m.group(1), Double.parseDouble(num));
        }
        if (out.isEmpty() && !s.isEmpty()) {
            throw new RuntimeException("no numeric fields parsed");
        }
        return out;
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "advanced_orchestration_agent",
            Settings.LLM_MODEL,
            "You are a senior business intelligence analyst. When given a research request, "
                + "systematically gather company data, market trends, and compute relevant metrics. "
                + "Then synthesize everything into a structured report with findings and recommendations.",
            new OrchestrationTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Produce a brief competitive analysis of OpenAI and Anthropic. "
                + "Include AI market trends and calculate the CAGR if the AI market grows "
                + "from $200B in 2024 to $1.8T by 2030."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
