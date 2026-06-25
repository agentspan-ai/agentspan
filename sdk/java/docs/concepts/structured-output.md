# Structured Output

Set `outputType(Class<?>)` and the agent returns a typed object instead of free text. The SDK
derives a JSON Schema from the class, the server constrains the LLM to it, and you deserialize the
result with `AgentResult.getOutput(Class)`.

```java
public class WeatherReport {
    public String city;
    public double temperature;
    public String condition;
    public String recommendation;
}

Agent agent = Agent.builder()
    .name("weather_reporter")
    .model("openai/gpt-4o-mini")
    .instructions("You are a weather reporter. Get the weather and provide a recommendation.")
    .tools(ToolRegistry.fromInstance(new WeatherTools()))
    .outputType(WeatherReport.class)
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What's the weather in NYC?");

    if (result.isSuccess()) {
        WeatherReport report = result.getOutput(WeatherReport.class);
        System.out.println(report.city + ": " + report.temperature + "°");
    }
}
```

## Notes

- The output class can be a plain POJO with public fields (as above), a Java `record`, or any
  type Jackson can deserialize.
- `getOutput()` (no argument) returns the raw value (a `String` or a `Map`). `getOutput(Class<T>)`
  deserializes via Jackson and transparently unwraps a `{"result": ...}` envelope if the server
  wrapped it, returning `null` when there is no output.
- Framework bridges that don't have a Java class handle (e.g. `OpenAIAgent`) take a type **name**
  string instead — see [OpenAI Agents SDK](../frameworks/openai.md#structured-output).
