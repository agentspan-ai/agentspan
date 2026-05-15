// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk04 — Sub-Agents.
//
// Multi-agent orchestration via ADK sub_agents. A coordinator delegates
// to specialist sub-agents (flight, hotel, advisory).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var flightAgent = GoogleADKAgent.Builder()
    .Name("flight_specialist")
    .Model(Settings.LlmModel)
    .Instruction("You are a flight specialist. Search for flights and present " +
                 "options clearly with prices and schedules.")
    .Tools(new FlightTools())
    .Build();

var hotelAgent = GoogleADKAgent.Builder()
    .Name("hotel_specialist")
    .Model(Settings.LlmModel)
    .Instruction("You are a hotel specialist. Search for hotels and present " +
                 "options with ratings and prices.")
    .Tools(new HotelTools())
    .Build();

var advisoryAgent = GoogleADKAgent.Builder()
    .Name("travel_advisory_specialist")
    .Model(Settings.LlmModel)
    .Instruction("You are a travel advisory specialist. Provide safety levels " +
                 "and visa requirements for destinations.")
    .Tools(new AdvisoryTools())
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("travel_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a travel planning coordinator. When a user wants to plan a trip:\n" +
        "1. Use the travel advisory specialist to check safety and visa info\n" +
        "2. Use the flight specialist to find flights\n" +
        "3. Use the hotel specialist to find accommodation\n" +
        "Route the user's request to the appropriate specialist.")
    .SubAgents(flightAgent, hotelAgent, advisoryAgent)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "I want to plan a trip to Japan. I need a flight from San Francisco " +
    "on 2025-04-15 and a hotel for 5 nights. Also, what's the travel advisory?");
result.PrintResult();

internal sealed class FlightTools
{
    [Tool(Name = "search_flights", Description = "Search for available flights.")]
    public Dictionary<string, object> SearchFlights(string origin, string destination, string date)
    {
        return new Dictionary<string, object>
        {
            ["flights"] = new List<Dictionary<string, object>>
            {
                new() { ["airline"] = "SkyLine",  ["departure"] = "08:00", ["arrival"] = "11:30", ["price"] = "$320" },
                new() { ["airline"] = "AirGlobe", ["departure"] = "14:00", ["arrival"] = "17:45", ["price"] = "$285" },
            },
            ["route"] = $"{origin} -> {destination}",
            ["date"]  = date,
        };
    }
}

internal sealed class HotelTools
{
    [Tool(Name = "search_hotels", Description = "Search for available hotels.")]
    public Dictionary<string, object> SearchHotels(string city, string checkin, string checkout)
    {
        return new Dictionary<string, object>
        {
            ["hotels"] = new List<Dictionary<string, object>>
            {
                new() { ["name"] = "Grand Plaza",      ["rating"] = 4.5, ["price"] = "$180/night" },
                new() { ["name"] = "City Comfort Inn", ["rating"] = 4.0, ["price"] = "$95/night"  },
                new() { ["name"] = "Boutique Lux",     ["rating"] = 4.8, ["price"] = "$250/night" },
            },
            ["city"]  = city,
            ["dates"] = $"{checkin} to {checkout}",
        };
    }
}

internal sealed class AdvisoryTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _advisories = new(StringComparer.OrdinalIgnoreCase)
    {
        ["japan"]     = new() { ["level"] = "Level 1 - Exercise Normal Precautions",   ["visa"] = "Visa-free for 90 days"       },
        ["france"]    = new() { ["level"] = "Level 2 - Exercise Increased Caution",    ["visa"] = "Schengen visa required"      },
        ["australia"] = new() { ["level"] = "Level 1 - Exercise Normal Precautions",   ["visa"] = "eVisitor visa required"      },
    };

    [Tool(Name = "get_travel_advisory", Description = "Get travel advisory information for a country.")]
    public Dictionary<string, object> GetTravelAdvisory(string country)
    {
        return _advisories.TryGetValue(country, out var v)
            ? v
            : new Dictionary<string, object> { ["level"] = "Unknown", ["visa"] = "Check embassy website" };
    }
}
