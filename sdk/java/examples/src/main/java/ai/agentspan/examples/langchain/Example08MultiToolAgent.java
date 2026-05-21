// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 08 — Multi-Tool Agent (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/08_multi_tool_agent.py</code>.
 * Combines tools for weather, finance, and news domains into a single agent
 * that selects the right tool based on the question.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Combining tools from multiple domains in one agent</li>
 *   <li>Agent selects the right tool based on the question type</li>
 *   <li>Handling multi-domain queries in a single request</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>Agentspan server with OpenAI credentials configured server-side.</li>
 * </ul>
 */
public class Example08MultiToolAgent {

    static class MultiDomainTools {

        private static final Map<String, String> WEATHER = Map.of(
            "new york", "72°F (22°C), partly cloudy, humidity 65%, light winds from SW.",
            "london",   "58°F (14°C), overcast with light rain, humidity 80%.",
            "tokyo",    "68°F (20°C), sunny, humidity 55%, calm winds.",
            "sydney",   "75°F (24°C), clear skies, humidity 50%, gentle sea breeze.",
            "paris",    "63°F (17°C), mostly cloudy, humidity 70%."
        );

        private static final Map<String, String> PRICES = Map.of(
            "AAPL",  "$182.50 (+1.2%)",
            "GOOGL", "$141.80 (-0.4%)",
            "MSFT",  "$378.20 (+0.8%)",
            "AMZN",  "$184.90 (+2.1%)",
            "TSLA",  "$248.30 (-1.5%)"
        );

        private static final Map<String, String> HEADLINES = Map.of(
            "technology", "AI model achieves human-level performance on coding benchmarks.",
            "climate",    "Global temperatures hit record highs for the third consecutive year.",
            "sports",     "Record-breaking athlete sets new world marathon record at 1:59:40.",
            "finance",    "Central bank holds interest rates steady amid cooling inflation.",
            "science",    "Researchers discover a new species of deep-sea bioluminescent fish."
        );

        @Tool(
            name = "get_weather",
            value = "Get current weather conditions for a city. "
                  + "Args: city — the city name (e.g., 'New York', 'London')."
        )
        public String getWeather(@P("city") String city) {
            String key = city == null ? "" : city.toLowerCase(Locale.ROOT);
            return WEATHER.getOrDefault(key, "Weather data unavailable for '" + city + "'.");
        }

        @Tool(
            name = "get_stock_price",
            value = "Look up the current stock price for a ticker symbol. "
                  + "Args: ticker — the stock ticker symbol (e.g., 'AAPL', 'GOOGL')."
        )
        public String getStockPrice(@P("ticker") String ticker) {
            String key = ticker == null ? "" : ticker.toUpperCase(Locale.ROOT);
            return PRICES.getOrDefault(key, "No price data for ticker '" + ticker + "'.");
        }

        @Tool(
            name = "get_news_headline",
            value = "Fetch the top news headline for a given topic. "
                  + "Args: topic — the news topic (e.g., 'technology', 'climate', 'sports')."
        )
        public String getNewsHeadline(@P("topic") String topic) {
            String key = topic == null ? "" : topic.toLowerCase(Locale.ROOT);
            return HEADLINES.getOrDefault(key, "No headlines found for topic '" + topic + "'.");
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
            model,
            "You are a multi-domain assistant with access to weather, stock, and news information.\n\n"
                + "What's the weather in Tokyo, the price of AAPL stock, and the latest technology headline?",
            new MultiDomainTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
