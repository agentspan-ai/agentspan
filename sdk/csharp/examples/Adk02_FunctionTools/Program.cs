// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk02 — Function Tools.
//
// Multiple Google ADK tools with typed parameters. The runtime reflects
// [Tool]-annotated methods and registers them as workers.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("travel_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a travel assistant. Help users with weather information, " +
        "temperature conversions, and timezone lookups. Be concise and accurate.")
    .Tools(new TravelTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "What's the weather in Tokyo right now? Convert the temperature to " +
    "Fahrenheit and tell me what timezone they're in.");
result.PrintResult();

internal sealed class TravelTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _weather =
        new(StringComparer.OrdinalIgnoreCase)
    {
        ["tokyo"]  = new() { ["temp_c"] = 22, ["condition"] = "Clear",         ["humidity"] = 65 },
        ["paris"]  = new() { ["temp_c"] = 18, ["condition"] = "Partly Cloudy", ["humidity"] = 72 },
        ["sydney"] = new() { ["temp_c"] = 25, ["condition"] = "Sunny",         ["humidity"] = 58 },
        ["mumbai"] = new() { ["temp_c"] = 32, ["condition"] = "Humid",         ["humidity"] = 85 },
    };

    private static readonly Dictionary<string, Dictionary<string, object>> _timezones =
        new(StringComparer.OrdinalIgnoreCase)
    {
        ["tokyo"]  = new() { ["timezone"] = "JST",  ["utc_offset"] = "+9:00"  },
        ["paris"]  = new() { ["timezone"] = "CET",  ["utc_offset"] = "+1:00"  },
        ["sydney"] = new() { ["timezone"] = "AEST", ["utc_offset"] = "+10:00" },
        ["mumbai"] = new() { ["timezone"] = "IST",  ["utc_offset"] = "+5:30"  },
    };

    [Tool(Name = "get_weather", Description = "Get the current weather for a city.")]
    public Dictionary<string, object> GetWeather(string city)
    {
        var data = _weather.TryGetValue(city, out var v)
            ? v
            : new Dictionary<string, object> { ["temp_c"] = 20, ["condition"] = "Unknown", ["humidity"] = 50 };
        var result = new Dictionary<string, object> { ["city"] = city };
        foreach (var (k, val) in data) result[k] = val;
        return result;
    }

    [Tool(Name = "convert_temperature", Description = "Convert temperature between Celsius and Fahrenheit.")]
    public Dictionary<string, object> ConvertTemperature(double temp_celsius, string to_unit)
    {
        var unit = string.IsNullOrEmpty(to_unit) ? "fahrenheit" : to_unit.ToLowerInvariant();
        if (unit == "fahrenheit")
        {
            var converted = temp_celsius * 9.0 / 5.0 + 32;
            return new Dictionary<string, object> { ["celsius"] = temp_celsius, ["fahrenheit"] = Math.Round(converted, 1) };
        }
        if (unit == "kelvin")
        {
            var converted = temp_celsius + 273.15;
            return new Dictionary<string, object> { ["celsius"] = temp_celsius, ["kelvin"] = Math.Round(converted, 1) };
        }
        return new Dictionary<string, object> { ["error"] = $"Unknown unit: {to_unit}" };
    }

    [Tool(Name = "get_time_zone", Description = "Get the timezone for a city.")]
    public Dictionary<string, object> GetTimeZone(string city)
    {
        return _timezones.TryGetValue(city, out var v)
            ? v
            : new Dictionary<string, object> { ["timezone"] = "Unknown", ["utc_offset"] = "Unknown" };
    }
}
