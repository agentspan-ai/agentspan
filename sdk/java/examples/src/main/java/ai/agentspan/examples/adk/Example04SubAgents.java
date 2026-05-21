// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 04 — Sub-Agents
 *
 * <p>Java port of <code>sdk/python/examples/adk/04_sub_agents.py</code>.
 *
 * <p>Demonstrates: multi-agent orchestration via native ADK
 * {@code subAgents(...)}. A coordinator delegates to specialist sub-agents
 * (flight, hotel, advisory). Tools are static methods registered via
 * {@link FunctionTool#create(Class, String)}.
 */
public class Example04SubAgents {

    // ── Flight tools ──────────────────────────────────────────────────────

    @Schema(description = "Search for available flights.")
    public static Map<String, Object> searchFlights(
            @Schema(name = "origin", description = "Origin city") String origin,
            @Schema(name = "destination", description = "Destination city") String destination,
            @Schema(name = "date", description = "Travel date") String date) {
        return Map.of(
            "flights", List.of(
                Map.of("airline", "SkyLine", "departure", "08:00", "arrival", "11:30", "price", "$320"),
                Map.of("airline", "AirGlobe", "departure", "14:00", "arrival", "17:45", "price", "$285")
            ),
            "route", origin + " → " + destination,
            "date", date
        );
    }

    // ── Hotel tools ───────────────────────────────────────────────────────

    @Schema(description = "Search for available hotels.")
    public static Map<String, Object> searchHotels(
            @Schema(name = "city", description = "City name") String city,
            @Schema(name = "checkin", description = "Check-in date") String checkin,
            @Schema(name = "checkout", description = "Check-out date") String checkout) {
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

    // ── Advisory tools ────────────────────────────────────────────────────

    @Schema(description = "Get travel advisory information for a country.")
    public static Map<String, Object> getTravelAdvisory(
            @Schema(name = "country", description = "Country name") String country) {
        Map<String, Map<String, Object>> advisories = new LinkedHashMap<>();
        advisories.put("japan", Map.of("level", "Level 1 - Exercise Normal Precautions", "visa", "Visa-free for 90 days"));
        advisories.put("france", Map.of("level", "Level 2 - Exercise Increased Caution", "visa", "Schengen visa required"));
        advisories.put("australia", Map.of("level", "Level 1 - Exercise Normal Precautions", "visa", "eVisitor visa required"));
        return advisories.getOrDefault(country.toLowerCase(),
            Map.of("level", "Unknown", "visa", "Check embassy website"));
    }

    public static void main(String[] args) {
        LlmAgent flightAgent = LlmAgent.builder()
            .name("flight_specialist")
            .description("Searches for flights and presents options with prices and schedules.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a flight specialist. Search for flights and present "
                + "options clearly with prices and schedules.")
            .tools(FunctionTool.create(Example04SubAgents.class, "searchFlights"))
            .build();

        LlmAgent hotelAgent = LlmAgent.builder()
            .name("hotel_specialist")
            .description("Searches for hotels and presents options with ratings and prices.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a hotel specialist. Search for hotels and present "
                + "options with ratings and prices.")
            .tools(FunctionTool.create(Example04SubAgents.class, "searchHotels"))
            .build();

        LlmAgent advisoryAgent = LlmAgent.builder()
            .name("travel_advisory_specialist")
            .description("Provides safety levels and visa requirements for destinations.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a travel advisory specialist. Provide safety levels "
                + "and visa requirements for destinations.")
            .tools(FunctionTool.create(Example04SubAgents.class, "getTravelAdvisory"))
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("travel_coordinator")
            .description("Coordinates flight, hotel, and travel-advisory specialists to plan a trip.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a travel planning coordinator. When a user wants to plan a trip:
                1. Use the travel advisory specialist to check safety and visa info
                2. Use the flight specialist to find flights
                3. Use the hotel specialist to find accommodation
                Route the user's request to the appropriate specialist.
                """)
            .subAgents(flightAgent, hotelAgent, advisoryAgent)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "I want to plan a trip to Japan. I need a flight from San Francisco "
            + "on 2025-04-15 and a hotel for 5 nights. Also, what's the travel advisory?");
        result.printResult();

        Agentspan.shutdown();
    }
}
