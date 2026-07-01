// Copyright (c) 2026 Agentspan
// Licensed under the MIT License.

using System.Net;
using System.Net.Http;
using System.Text;
using Conductor.AI;
using Conductor.AI.Scheduling;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Fix #6 — name-keyed RunNowAsync(name) and a synchronous wait variant
/// mirroring Python run_now(name, wait=True).
/// </summary>
public class SchedulesRunNowTests
{
    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, (HttpStatusCode, string)> _respond;
        public readonly List<string> Requests = new();
        public StubHandler(Func<HttpRequestMessage, (HttpStatusCode, string)> respond) => _respond = respond;

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Requests.Add($"{request.Method} {request.RequestUri!.PathAndQuery}");
            var (code, body) = _respond(request);
            return Task.FromResult(new HttpResponseMessage(code)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            });
        }
    }

    private const string ScheduleJson = """
    {
      "name": "digest-daily",
      "cronExpression": "0 0 9 * * ?",
      "zoneId": "UTC",
      "paused": false,
      "startWorkflowRequest": { "name": "digest", "input": { "topic": "ai" } }
    }
    """;

    [Fact]
    public async Task RunNowAsync_by_name_fetches_then_runs()
    {
        var handler = new StubHandler(req =>
        {
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.Contains("/scheduler/schedules/"))
                return (HttpStatusCode.OK, ScheduleJson);
            if (req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.StartsWith("/workflow/"))
                return (HttpStatusCode.OK, "\"wf-123\"");
            return (HttpStatusCode.NotFound, "");
        });
        var schedules = new Schedules(new HttpClient(handler), "http://localhost:8080");

        var execId = await schedules.RunNowAsync("digest-daily");

        Assert.Equal("wf-123", execId);
        Assert.Contains(handler.Requests, r => r.StartsWith("GET /scheduler/schedules/digest-daily"));
        Assert.Contains(handler.Requests, r => r.StartsWith("POST /workflow/digest"));
    }

    [Fact]
    public async Task RunNowAsync_wait_polls_to_completion_and_returns_result()
    {
        int poll = 0;
        var handler = new StubHandler(req =>
        {
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.Contains("/scheduler/schedules/"))
                return (HttpStatusCode.OK, ScheduleJson);
            if (req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.StartsWith("/workflow/"))
                return (HttpStatusCode.OK, "\"wf-123\"");
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.StartsWith("/workflow/wf-123"))
            {
                poll++;
                return poll < 2
                    ? (HttpStatusCode.OK, "{\"status\":\"RUNNING\"}")
                    : (HttpStatusCode.OK, "{\"status\":\"COMPLETED\",\"output\":{\"result\":\"done\"}}");
            }
            return (HttpStatusCode.NotFound, "");
        });
        var schedules = new Schedules(new HttpClient(handler), "http://localhost:8080");

        var result = await schedules.RunNowAsync("digest-daily", wait: true, pollIntervalMs: 1);

        Assert.Equal(Status.Completed, result.Status);
        Assert.True(poll >= 2);
    }
}
