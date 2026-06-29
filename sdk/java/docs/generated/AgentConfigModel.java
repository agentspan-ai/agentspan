// AUTO-GENERATED from agent-schema.json by generate.py — do not edit.
import java.util.List;
import java.util.Map;

public final class AgentConfigModel {
  private AgentConfigModel() {}

  public record AgentConfig(String name, String description, String model, Boolean external, String baseUrl, Object instructions, String introduction, List<Tool> tools, List<AgentConfig> agents, String strategy, Object router, List<Guardrail> guardrails, Integer maxTurns, Integer maxTokens, Double temperature, Integer timeoutSeconds, String reasoningEffort, Integer contextWindowBudget, ThinkingConfig thinkingConfig, Memory memory, Termination termination, OutputType outputType, List<Handoff> handoffs, Map<String, Object> allowedTransitions, List<Callback> callbacks, Gate gate, WorkerRef stopWhen, Boolean enablePlanning, AgentConfig planner, AgentConfig fallback, Integer fallbackMaxTurns, List<PlannerContextEntry> plannerContext, Map<String, Object> planSource, Boolean synthesize, Boolean stateful, String sessionId, String includeContents, List<String> requiredTools, List<PrefillTool> prefillTools, List<String> credentials, Map<String, Object> metadata, Boolean localCodeExecution, CodeExecution codeExecution, CliConfig cliConfig, List<String> maskedFields) {}
  public record PromptTemplate(String type, String name, Map<String, Object> variables, Integer version) {}
  public record Tool(String name, String description, Map<String, Object> inputSchema, Map<String, Object> outputSchema, String toolType, Boolean approvalRequired, Boolean stateful, Integer timeoutSeconds, Integer maxCalls, Map<String, Object> config, List<Guardrail> guardrails) {}
  public record Guardrail(String name, String guardrailType, String position, String onFail, Integer maxRetries, String taskName, List<String> patterns, String mode, String message, String model, String policy, Integer maxTokens) {}
  public record Termination(String type, String text, Boolean caseSensitive, String stopMessage, Integer maxMessages, Integer maxTotalTokens, Integer maxPromptTokens, Integer maxCompletionTokens, List<Termination> conditions) {}
  public record Handoff(String type, String target, String toolName, String resultContains, String text, String taskName) {}
  public record Callback(String position, String taskName) {}
  public record Memory(List<Message> messages, Integer maxMessages) {}
  public record Message(String role, String message) {}
  public record CodeExecution(Boolean enabled, List<String> allowedLanguages, List<String> allowedCommands, Integer timeout) {}
  public record CliConfig(Boolean enabled, List<String> allowedCommands, Integer timeout, Boolean allowShell, String workingDir) {}
  public record ThinkingConfig(Boolean enabled, Integer budgetTokens) {}
  public record PrefillTool(String toolName, Map<String, Object> arguments) {}
  public record PlannerContextEntry(String text, String url, Map<String, Object> headers, Boolean required, Integer maxBytes) {}
  public record OutputType(Map<String, Object> schema, String className) {}
  public record Gate(String type, String text, Boolean caseSensitive, String taskName) {}
  public record WorkerRef(String taskName) {}
}
