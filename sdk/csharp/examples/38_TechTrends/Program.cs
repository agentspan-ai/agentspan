// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Tech Trend Analyzer — multi-agent research + analysis + PDF pipeline.
//
// Compares two programming languages using real data from HackerNews,
// PyPI Stats, npm, and Wikipedia. Architecture:
//
//   researcher >> analyst >> pdf_generator
//
// The pdf_generator uses a server-side GENERATE_PDF tool — no worker needed.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Net.Http.Json;
using System.Text.Json;
using System.Web;
using Agentspan;
using Agentspan.Examples;

// ── Researcher tools ──────────────────────────────────────────

var researcher = new Agent("hn_researcher_38")
{
    Model        = Settings.LlmModel,
    MaxTokens    = 4000,
    Instructions =
        "You are a technology research assistant. You MUST call tools to gather real data. " +
        "Do NOT describe what you are going to do — just call the tools immediately.\n\n" +
        "REQUIRED STEPS (call tools in this exact order):\n" +
        "1. Call search_hackernews(query='Python programming language', maxResults=8)\n" +
        "2. Call search_hackernews(query='Rust programming language', maxResults=8)\n" +
        "3. From the Python results, call get_hn_story_comments on the story with the most comments\n" +
        "4. From the Rust results, call get_hn_story_comments on the story with the most comments\n" +
        "5. Call get_wikipedia_summary(topic='Python (programming language)')\n" +
        "6. Call get_wikipedia_summary(topic='Rust (programming language)')\n\n" +
        "After ALL 6 tool calls, write a structured report with REAL data.",
    Tools = ToolRegistry.FromInstance(new ResearcherTools()),
};

// ── Analyst tools ─────────────────────────────────────────────

var analyst = new Agent("hn_analyst_38")
{
    Model        = Settings.LlmModel,
    MaxTokens    = 4000,
    Instructions =
        "You are a technology trend analyst. You MUST call tools — do not describe what " +
        "you will do, just do it.\n\n" +
        "REQUIRED STEPS:\n" +
        "1. Call fetch_pypi_downloads(package='pip')\n" +
        "2. Call fetch_pypi_downloads(package='maturin')\n" +
        "3. Call fetch_npm_downloads(package='wasm-pack')\n" +
        "4. Count Python vs Rust stories and compare with compare_numbers\n\n" +
        "After ALL tool calls, write a final markdown analysis report.",
    Tools = ToolRegistry.FromInstance(new AnalystTools38()),
};

// ── PDF generator (server-side tool, no worker needed) ────────

var pdfGenerator = new Agent("pdf_report_generator_38")
{
    Model        = Settings.LlmModel,
    MaxTokens    = 4000,
    Instructions =
        "You receive a markdown report. Your ONLY job is to call the generate_pdf " +
        "tool with the full markdown content to produce a PDF document. " +
        "Pass the entire report as the 'markdown' parameter.",
    Tools = [MediaTools.Pdf(
        name:        "generate_pdf",
        description: "Generate a PDF report from markdown content.")],
};

// ── Pipeline ──────────────────────────────────────────────────

var pipeline = researcher >> analyst >> pdfGenerator;

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "Compare Python and Rust: which has stronger developer mindshare and " +
    "ecosystem momentum right now? Use real HackerNews data and package " +
    "download statistics to support your analysis.");

result.PrintResult();

// ── Researcher tool class ─────────────────────────────────────

internal sealed class ResearcherTools
{
    private static readonly HttpClient Http = new();

    [Tool("Search HackerNews for stories about a technology topic.")]
    public async Task<Dictionary<string, object>> SearchHackernews(string query, int maxResults = 8)
    {
        maxResults = Math.Clamp(maxResults, 1, 20);
        var url = $"https://hn.algolia.com/api/v1/search?query={HttpUtility.UrlEncode(query)}&tags=story&hitsPerPage={maxResults}";
        try
        {
            using var resp = await Http.GetAsync(url);
            var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
            var stories = data.GetProperty("hits").EnumerateArray()
                .Select(h => new Dictionary<string, object>
                {
                    ["id"]           = h.TryGetProperty("objectID", out var id)   ? id.GetString()! : "",
                    ["title"]        = h.TryGetProperty("title", out var t)       ? t.GetString()!  : "",
                    ["points"]       = h.TryGetProperty("points", out var p)      ? p.GetInt32()    : 0,
                    ["num_comments"] = h.TryGetProperty("num_comments", out var c)? c.GetInt32()    : 0,
                    ["author"]       = h.TryGetProperty("author", out var a)      ? a.GetString()!  : "",
                }).Cast<object>().ToList();
            return new() { ["query"] = query, ["stories"] = stories, ["total_found"] = data.GetProperty("nbHits").GetInt32() };
        }
        catch (Exception ex) { return new() { ["query"] = query, ["error"] = ex.Message, ["stories"] = new List<object>() }; }
    }

    [Tool("Fetch the top comments for a HackerNews story by its ID.")]
    public async Task<Dictionary<string, object>> GetHnStoryComments(string storyId)
    {
        try
        {
            using var resp = await Http.GetAsync($"https://hn.algolia.com/api/v1/items/{storyId}");
            var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
            var comments = data.GetProperty("children").EnumerateArray().Take(8)
                .Select(c => new Dictionary<string, object>
                {
                    ["author"] = c.TryGetProperty("author", out var a) ? a.GetString()! : "",
                    ["text"]   = c.TryGetProperty("text", out var tx)  ? System.Text.RegularExpressions.Regex.Replace(tx.GetString() ?? "", "<[^>]+>", " ").Trim()[..Math.Min(400, (tx.GetString() ?? "").Length)] : "",
                }).Cast<object>().ToList();
            return new() { ["story_id"] = storyId, ["top_comments"] = comments };
        }
        catch (Exception ex) { return new() { ["story_id"] = storyId, ["error"] = ex.Message }; }
    }

    [Tool("Fetch the Wikipedia introduction for a technology or topic.")]
    public async Task<Dictionary<string, object>> GetWikipediaSummary(string topic)
    {
        var encoded = HttpUtility.UrlEncode(topic.Replace(" ", "_"));
        var req = new HttpRequestMessage(HttpMethod.Get, $"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}");
        req.Headers.Add("User-Agent", "TechTrendAnalyzer/1.0");
        try
        {
            using var resp = await Http.SendAsync(req);
            var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
            var extract = data.TryGetProperty("extract", out var e) ? e.GetString() ?? "" : "";
            return new()
            {
                ["topic"]       = topic,
                ["description"] = data.TryGetProperty("description", out var d) ? d.GetString()! : "",
                ["extract"]     = extract.Length > 800 ? extract[..800] : extract,
            };
        }
        catch (Exception ex) { return new() { ["topic"] = topic, ["error"] = ex.Message }; }
    }
}

// ── Analyst tool class ────────────────────────────────────────

internal sealed class AnalystTools38
{
    private static readonly HttpClient Http = new();

    [Tool("Fetch recent PyPI download statistics for a Python package.")]
    public async Task<Dictionary<string, object>> FetchPypiDownloads(string package)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, $"https://pypistats.org/api/packages/{HttpUtility.UrlEncode(package)}/recent");
        req.Headers.Add("User-Agent", "Mozilla/5.0 (compatible; research-bot/1.0)");
        try
        {
            using var resp = await Http.SendAsync(req);
            var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
            var row = data.GetProperty("data");
            return new()
            {
                ["package"]    = package,
                ["last_day"]   = row.TryGetProperty("last_day",   out var d) ? d.GetInt64() : 0,
                ["last_week"]  = row.TryGetProperty("last_week",  out var w) ? w.GetInt64() : 0,
                ["last_month"] = row.TryGetProperty("last_month", out var m) ? m.GetInt64() : 0,
            };
        }
        catch (Exception ex) { return new() { ["package"] = package, ["error"] = ex.Message }; }
    }

    [Tool("Fetch last-month download count for an npm package.")]
    public async Task<Dictionary<string, object>> FetchNpmDownloads(string package)
    {
        try
        {
            using var resp = await Http.GetAsync($"https://api.npmjs.org/downloads/point/last-month/{HttpUtility.UrlEncode(package)}");
            var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
            return new()
            {
                ["package"]              = package,
                ["downloads_last_month"] = data.TryGetProperty("downloads", out var d) ? d.GetInt64() : 0,
            };
        }
        catch (Exception ex) { return new() { ["package"] = package, ["error"] = ex.Message }; }
    }

    [Tool("Compute ratio and percentage difference between two numeric values.")]
    public Dictionary<string, object> CompareNumbers(string labelA, double valueA, string labelB, double valueB, string metric)
    {
        double ratio   = valueB == 0 ? (valueA > 0 ? double.PositiveInfinity : 1.0) : Math.Round(valueA / valueB, 3);
        double pctDiff = valueB == 0 ? 100.0 : Math.Round(Math.Abs(valueA - valueB) / valueB * 100, 1);
        return new()
        {
            ["metric"]         = metric,
            [labelA]           = valueA,
            [labelB]           = valueB,
            ["ratio"]          = $"{labelA}/{labelB} = {ratio}",
            ["pct_difference"] = $"{pctDiff}%",
            ["winner"]         = valueA >= valueB ? labelA : labelB,
        };
    }
}
