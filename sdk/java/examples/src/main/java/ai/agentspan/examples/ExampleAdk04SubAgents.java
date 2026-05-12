// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 04 — Sub-Agents
 *
 * <p>Java port of <code>sdk/python/examples/adk/04_sub_agents.py</code>.
 *
 * <p>Demonstrates: multi-agent orchestration via ADK {@code sub_agents}. A
 * coordinator delegates to specialist sub-agents (flight, hotel, advisory).
 * The server normalizer maps sub_agents to agents + strategy="handoff".
 */
public class ExampleAdk04SubAgents {

    // ── Specialist tools ──────────────────────────────────────────────────

    public static class FlightTools {
        @Tool(name = "search_flights", value = "Search for available flights.")
        public Map<String, Object> searchFlights(
                @P("origin") String origin,
                @P("destination") String destination,
                @P("date") String date) {
            return Map.of(
                "flights", List.of(
                    Map.of("airline", "SkyLine", "departure", "08:00", "arrival", "11:30", "price", "$320"),
                    Map.of("airline", "AirGlobe", "departure", "14:00", "arrival", "17:45", "price", "$285")
                ),
                "route", origin + " → " + destination,
                "date", date
            );
        }
    }

    public static class HotelTools {
        @Tool(name = "search_hotels", value = "Search for available hotels.")
        public Map<String, Object> searchHotels(
                @P("city") String city,
                @P("checkin") String checkin,
                @P("checkout") String checkout) {
            return Map.of(
                "hotels", List.of(
                    Map.of("name", "Grand Plaza", "rating", 4.5, "price", "$180/night"),
                    Map.of("name", "City Comfort Inn", "rating", 4.0, "price", "$95/night"),
                    Map.of("name", "Boutique Lux", "rating", 4.8, "price", "$250/night")
                ),
                "city", city,
                "dates", checkin + " to " + checkout
            );
        }
    }

    public static class AdvisoryTools {
        @Tool(name = "get_travel_advisory", value = "Get travel advisory information for a country.")
        public Map<String, Object> getTravelAdvisory(@P("country") String country) {
            Map<String, Map<String, Object>> advisories = new LinkedHashMap<>();
            advisories.put("japan", Map.of("level", "Level 1 - Exercise Normal Precautions", "visa", "Visa-free for 90 days"));
            advisories.put("france", Map.of("level", "Level 2 - Exercise Increased Caution", "visa", "Schengen visa required"));
            advisories.put("australia", Map.of("level", "Level 1 - Exercise Normal Precautions", "visa", "eVisitor visa required"));
            return advisories.getOrDefault(country.toLowerCase(),
                Map.of("level", "Unknown", "visa", "Check embassy website"));
        }
    }

    public static void main(String[] args) {
        Agent flightAgent = GoogleADKAgent.builder()
            .name("flight_specialist")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a flight specialist. Search for flights and present "
                + "options clearly with prices and schedules.")
            .tools(new FlightTools())
            .build();

        Agent hotelAgent = GoogleADKAgent.builder()
            .name("hotel_specialist")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a hotel specialist. Search for hotels and present "
                + "options with ratings and prices.")
            .tools(new HotelTools())
            .build();

        Agent advisoryAgent = GoogleADKAgent.builder()
            .name("travel_advisory_specialist")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a travel advisory specialist. Provide safety levels "
                + "and visa requirements for destinations.")
            .tools(new AdvisoryTools())
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("travel_coordinator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a travel planning coordinator. When a user wants to plan a trip:\n"
                + "1. Use the travel advisory specialist to check safety and visa info\n"
                + "2. Use the flight specialist to find flights\n"
                + "3. Use the hotel specialist to find accommodation\n"
                + "Route the user's request to the appropriate specialist.")
            .subAgents(flightAgent, hotelAgent, advisoryAgent)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "I want to plan a trip to Japan. I need a flight from San Francisco "
            + "on 2025-04-15 and a hotel for 5 nights. Also, what's the travel advisory?");
        result.printResult();

        Agentspan.shutdown();
    }
}
