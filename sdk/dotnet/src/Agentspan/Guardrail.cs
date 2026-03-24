namespace Agentspan;

public enum GuardrailPosition { Input, Output }
public enum GuardrailOnFail { Retry, Raise, Fix, Human }

public sealed record GuardrailResult(bool Passed, string Message = "", string? FixedOutput = null);

public sealed class Guardrail
{
    public string Name { get; }
    public GuardrailPosition Position { get; }
    public GuardrailOnFail OnFail { get; }
    public int MaxRetries { get; }
    public Func<string, GuardrailResult>? Func { get; }
    public bool IsExternal => Func == null;

    public Guardrail(
        Func<string, GuardrailResult>? func,
        GuardrailPosition position = GuardrailPosition.Output,
        GuardrailOnFail onFail = GuardrailOnFail.Retry,
        string? name = null,
        int maxRetries = 3)
    {
        if (func == null && name == null) throw new ArgumentException("Either func or name must be provided");
        if (maxRetries < 1) throw new ArgumentException("maxRetries must be >= 1");

        Func = func;
        Position = position;
        OnFail = onFail;
        Name = name ?? func?.Method.Name ?? "guardrail";
        MaxRetries = maxRetries;
    }

    public GuardrailResult Check(string content) =>
        Func?.Invoke(content) ?? throw new InvalidOperationException("Cannot call Check() on external guardrail");
}
