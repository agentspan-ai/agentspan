// Guardrails — output validation with PII detection and content policy
// Demonstrates custom guardrail functions that check agent output.
using System.Text.RegularExpressions;
using Agentspan;
using AgentspanExamples;

// PII detection guardrail — blocks responses containing SSNs, credit cards, or emails
static GuardrailResult PiiDetector(string content)
{
    // Check for SSN patterns (XXX-XX-XXXX)
    if (Regex.IsMatch(content, @"\b\d{3}-\d{2}-\d{4}\b"))
        return new GuardrailResult(false, "Output contains what appears to be a Social Security Number");

    // Check for credit card patterns
    if (Regex.IsMatch(content, @"\b(?:\d{4}[- ]){3}\d{4}\b"))
        return new GuardrailResult(false, "Output contains what appears to be a credit card number");

    // Check for email addresses (allow generic ones but flag personal-looking ones)
    var emailMatches = Regex.Matches(content, @"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b");
    foreach (Match match in emailMatches)
    {
        var email = match.Value.ToLower();
        // Flag non-generic emails
        if (!email.Contains("example") && !email.Contains("test") && !email.Contains("sample"))
            return new GuardrailResult(false, $"Output contains a real email address: {email}");
    }

    // Check for phone numbers
    if (Regex.IsMatch(content, @"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"))
        return new GuardrailResult(false, "Output contains what appears to be a phone number");

    return new GuardrailResult(true, "No PII detected");
}

// Content length guardrail — ensures responses aren't too short
static GuardrailResult MinLengthCheck(string content)
{
    if (content.Trim().Length < 50)
        return new GuardrailResult(false, $"Response too short ({content.Trim().Length} chars). Minimum 50 characters required.");
    return new GuardrailResult(true, "Length check passed");
}

// Profanity/tone guardrail — basic check for unprofessional language
static GuardrailResult ToneCheck(string content)
{
    var unprofessionalPhrases = new[] { "stupid question", "obviously", "you should know", "duh" };
    foreach (var phrase in unprofessionalPhrases)
    {
        if (content.Contains(phrase, StringComparison.OrdinalIgnoreCase))
            return new GuardrailResult(false, $"Output contains unprofessional language: '{phrase}'");
    }
    return new GuardrailResult(true, "Tone check passed");
}

// Build guardrails
var guardrails = new[]
{
    new Guardrail(PiiDetector, GuardrailPosition.Output, GuardrailOnFail.Retry, "pii_detector", maxRetries: 3),
    new Guardrail(MinLengthCheck, GuardrailPosition.Output, GuardrailOnFail.Retry, "min_length_check", maxRetries: 2),
    new Guardrail(ToneCheck, GuardrailPosition.Output, GuardrailOnFail.Raise, "tone_check", maxRetries: 1),
};

var agent = new Agent(
    name: "customer_service_agent",
    model: Settings.LlmModel,
    instructions: """
        You are a professional customer service agent for a financial services company.
        - Always respond professionally and empathetically
        - Never include real personal information in responses
        - Provide helpful, actionable guidance
        - Keep responses concise but complete
        """,
    guardrails: guardrails
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

// Test the guardrails locally before sending to server
Console.WriteLine("=== Testing Guardrails Locally ===\n");

var testCases = new[]
{
    ("PII Test", "Your account number is 123-45-6789 and card 4532-1234-5678-9012."),
    ("Length Test", "OK."),
    ("Tone Test", "Obviously you should know how to reset your password, duh."),
    ("Clean Response", "Thank you for reaching out. To reset your password, please visit our secure portal at example.com/reset and follow the verification steps. If you need further assistance, our support team is available 24/7.")
};

foreach (var (name, testContent) in testCases)
{
    Console.WriteLine($"Test: {name}");
    Console.WriteLine($"Content: \"{testContent[..Math.Min(60, testContent.Length)]}...\"");
    foreach (var g in guardrails)
    {
        var checkResult = g.Check(testContent);
        var status = checkResult.Passed ? "PASS" : "FAIL";
        Console.WriteLine($"  [{status}] {g.Name}: {checkResult.Message}");
    }
    Console.WriteLine();
}

Console.WriteLine("=== Running Agent with Guardrails ===\n");
using var runtime = new AgentRuntime(config);
var result = runtime.Run(
    agent,
    "A customer is asking how to update their billing information on their account."
);
result.PrintResult();
