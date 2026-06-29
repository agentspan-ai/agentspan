// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Fix #8 — ApiTools.Create ${NAME} credential validation, mirroring Python
/// api_tool: every ${NAME} placeholder in headers must be declared in credentials.
/// </summary>
public class ApiToolsTests
{
    [Fact]
    public void Undeclared_placeholder_throws()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            ApiTools.Create(
                url: "https://api.stripe.com/openapi.json",
                headers: new Dictionary<string, string> { ["Authorization"] = "Bearer ${STRIPE_KEY}" },
                credentials: null));
        Assert.Contains("STRIPE_KEY", ex.Message);
    }

    [Fact]
    public void Declared_placeholder_passes()
    {
        var td = ApiTools.Create(
            url: "https://api.stripe.com/openapi.json",
            headers: new Dictionary<string, string> { ["Authorization"] = "Bearer ${STRIPE_KEY}" },
            credentials: ["STRIPE_KEY"]);
        Assert.Equal("api", td.ToolType);
        Assert.Contains("STRIPE_KEY", td.Credentials);
    }

    [Fact]
    public void No_headers_no_validation()
    {
        var td = ApiTools.Create(url: "https://api.example.com/openapi.json");
        Assert.NotNull(td);
    }

    [Fact]
    public void Multiple_placeholders_one_missing_throws()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            ApiTools.Create(
                url: "https://x",
                headers: new Dictionary<string, string>
                {
                    ["Authorization"] = "Bearer ${A}",
                    ["X-Extra"] = "${B}",
                },
                credentials: ["A"]));
        Assert.Contains("B", ex.Message);
    }
}
