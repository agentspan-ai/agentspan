// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example Lc4j 24 — Output Parsers (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/24_output_parsers.py</code>.
 *
 * <p>Demonstrates structured-output style tools: ingredient lookup,
 * comma-list parsing into a numbered list, and regex-based extraction
 * of date / amount / email fields from free text.
 *
 * <p>Note: Python uses LangChain's {@code CommaSeparatedListOutputParser} and
 * {@code PydanticOutputParser}. The Java port uses prompt-based JSON return
 * shapes plus consumer-side Jackson deserialization — LangChain4j's
 * {@code AiServices} typed-return analog isn't applicable in
 * {@link Agentspan#run(ChatModel, String, Object...)} extraction mode
 * (server-side LLM loop).
 */
public class Example24OutputParsers {

    /** Tiny record-like value object for demonstrating structured returns. */
    static final class ExtractedFields {
        final String date;
        final String amount;
        final String email;

        ExtractedFields(String date, String amount, String email) {
            this.date = date;
            this.amount = amount;
            this.email = email;
        }
    }

    static final Map<String, String> INGREDIENTS = new LinkedHashMap<>();

    static {
        INGREDIENTS.put("pasta carbonara",
            "spaghetti, guanciale, eggs, pecorino romano, black pepper");
        INGREDIENTS.put("caesar salad",
            "romaine lettuce, croutons, parmesan, caesar dressing, anchovies");
        INGREDIENTS.put("chocolate chip cookies",
            "flour, butter, sugar, eggs, vanilla, chocolate chips, baking soda, salt");
        INGREDIENTS.put("chicken curry",
            "chicken, curry powder, coconut milk, onion, garlic, ginger, tomatoes, spices");
        INGREDIENTS.put("guacamole",
            "avocado, lime juice, cilantro, red onion, jalapeño, salt, tomato");
    }

    public static class OutputParserTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "get_ingredients",
            value = "Return the main ingredients for a dish as a comma-separated list."
        )
        public String getIngredients(@dev.langchain4j.agent.tool.P("dish") String dish) {
            String key = dish == null ? "" : dish.toLowerCase(Locale.ROOT);
            String value = INGREDIENTS.get(key);
            if (value != null) return value;
            return "No recipe found for '" + dish + "'.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "parse_as_list",
            value = "Parse a comma-separated string into a numbered list."
        )
        public String parseAsList(@dev.langchain4j.agent.tool.P("text") String text) {
            String src = text == null ? "" : text;
            String[] parts = src.split(",");
            List<String> items = new ArrayList<>();
            for (String p : parts) {
                String t = p.trim();
                if (!t.isEmpty()) items.add(t);
            }
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < items.size(); i++) {
                if (i > 0) out.append("\n");
                out.append(i + 1).append(". ").append(items.get(i));
            }
            return out.toString();
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "extract_structured_data",
            value = "Extract structured data fields (name, date, amount) from free text."
        )
        public String extractStructuredData(@dev.langchain4j.agent.tool.P("text") String text) {
            // Python uses PydanticOutputParser; Java port uses prompt-based JSON return
            // + Jackson deserialization on the consumer side.
            String t = text == null ? "" : text;
            Map<String, String> result = new LinkedHashMap<>();

            Pattern datePattern = Pattern.compile(
                "\\b(\\d{4}-\\d{2}-\\d{2}|\\d{1,2}/\\d{1,2}/\\d{2,4})\\b");
            Matcher dateMatch = datePattern.matcher(t);
            if (dateMatch.find()) result.put("date", dateMatch.group(0));

            Pattern amountPattern = Pattern.compile(
                "\\$[\\d,]+(?:\\.\\d{2})?|\\b\\d+(?:\\.\\d{2})?\\s*(?:dollars?|USD)\\b",
                Pattern.CASE_INSENSITIVE);
            Matcher amountMatch = amountPattern.matcher(t);
            if (amountMatch.find()) result.put("amount", amountMatch.group(0));

            Pattern emailPattern = Pattern.compile(
                "\\b[\\w.+-]+@[\\w-]+\\.\\w{2,}\\b");
            Matcher emailMatch = emailPattern.matcher(t);
            if (emailMatch.find()) result.put("email", emailMatch.group(0));

            if (result.isEmpty()) {
                return "No structured data fields (date, amount, email) found in text.";
            }
            return toJsonString(result);
        }
    }

    /** Minimal indent-2 JSON encoder so the tool output matches Python's json.dumps(indent=2). */
    private static String toJsonString(Map<String, String> map) {
        StringBuilder sb = new StringBuilder("{\n");
        int i = 0;
        for (Map.Entry<String, String> e : map.entrySet()) {
            sb.append("  \"").append(escape(e.getKey())).append("\": \"")
                .append(escape(e.getValue())).append("\"");
            if (i < map.size() - 1) sb.append(",");
            sb.append("\n");
            i++;
        }
        sb.append("}");
        return sb.toString();
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    public static void main(String[] args) {
        // Demonstrate the record-like value object so it isn't unused.
        @SuppressWarnings("unused")
        ExtractedFields example = new ExtractedFields("2025-03-15", "$249.99", "billing@example.com");

        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Python uses the shorter prompt below — fold it into the user
        // message via the drop-in overload for parity.
        AgentResult result = Agentspan.run(
            model,
            "You are a data extraction and formatting assistant. "
                + "Use tools to retrieve, parse, and structure information clearly.\n\n"
                + "Get the ingredients for pasta carbonara and format them as a numbered list. "
                + "Also extract any structured data from: "
                + "'Invoice #1234 dated 2025-03-15, amount $249.99, contact billing@example.com'",
            new OutputParserTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
