// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 19 — AgentAuthHandler: the control-plane client must mint a JWT from
// key+secret and send it as X-Authorization (the Orkes contract), matching the
// Python/TS SDKs. No server needed — the /token mint and the downstream request
// are both stubbed with in-memory handlers. Deterministic; fail-first validated.

using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace Agentspan.E2eTests;

public sealed class Suite19_AuthHeader
{
    // A base64url JWT payload with a far-future exp so the cache holds.
    private const long FarFutureExp = 4102444800; // 2100-01-01
    private static string FakeJwt(long exp)
    {
        string B64Url(string s)
        {
            var b = Convert.ToBase64String(Encoding.UTF8.GetBytes(s));
            return b.TrimEnd('=').Replace('+', '-').Replace('/', '_');
        }
        return $"{B64Url("{\"alg\":\"HS256\"}")}.{B64Url($"{{\"exp\":{exp}}}")}.sig";
    }

    /// <summary>Captures the X-Authorization header seen on each downstream request.</summary>
    private sealed class CapturingHandler : HttpMessageHandler
    {
        public readonly List<string?> SeenAuth = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            SeenAuth.Add(request.Headers.TryGetValues("X-Authorization", out var v)
                ? string.Join(",", v) : null);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
            });
        }
    }

    /// <summary>Stubs POST {server}/token, counting mint calls.</summary>
    private sealed class TokenMintHandler : HttpMessageHandler
    {
        public int MintCount;
        private readonly string _token;
        public TokenMintHandler(string token) => _token = token;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Assert.EndsWith("/token", request.RequestUri!.AbsolutePath);
            Interlocked.Increment(ref MintCount);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent($"{{\"token\":\"{_token}\"}}", Encoding.UTF8, "application/json"),
            });
        }
    }

    private static (HttpClient client, CapturingHandler cap, TokenMintHandler mint) BuildClient(
        string? key, string? secret, string token)
    {
        var cap  = new CapturingHandler();
        var mint = new TokenMintHandler(token);
        var auth = new AgentAuthHandler("http://server/api", key, secret, tokenHandler: mint)
        {
            InnerHandler = cap,
        };
        return (new HttpClient(auth), cap, mint);
    }

    // ── 19.1  key+secret → minted JWT in X-Authorization, cached ──────────

    [Fact]
    public async Task KeySecret_MintsJwt_SendsXAuthorization_AndCaches()
    {
        var jwt = FakeJwt(FarFutureExp);
        var (client, cap, mint) = BuildClient("my-key", "my-secret", jwt);

        await client.GetAsync("http://server/api/agent/anything");
        await client.GetAsync("http://server/api/agent/anything");

        Assert.Equal(2, cap.SeenAuth.Count);
        Assert.All(cap.SeenAuth, h => Assert.Equal(jwt, h));
        Assert.Equal(1, mint.MintCount); // minted once, reused from cache
    }

    // ── 19.2  explicit key, no secret → passed through verbatim (no mint) ─

    [Fact]
    public async Task KeyOnly_TreatedAsToken_NoMint()
    {
        var (client, cap, mint) = BuildClient("ready-token", null, "unused");
        await client.GetAsync("http://server/api/agent/anything");

        Assert.Equal("ready-token", cap.SeenAuth[0]);
        Assert.Equal(0, mint.MintCount);
    }

    // ── 19.3  no credentials → no auth header (OSS anonymous) ─────────────

    [Fact]
    public async Task NoCreds_NoAuthHeader()
    {
        var (client, cap, mint) = BuildClient(null, null, "unused");
        await client.GetAsync("http://server/api/agent/anything");

        Assert.Null(cap.SeenAuth[0]);
        Assert.Equal(0, mint.MintCount);
    }

    // ── 19.4  JWT exp decode ──────────────────────────────────────────────

    [Fact]
    public void DecodeJwtExp_ParsesExp()
    {
        Assert.Equal(FarFutureExp, AgentAuthHandler.DecodeJwtExp(FakeJwt(FarFutureExp)));
        Assert.Null(AgentAuthHandler.DecodeJwtExp("not-a-jwt"));
        Assert.Null(AgentAuthHandler.DecodeJwtExp(null));
    }
}
