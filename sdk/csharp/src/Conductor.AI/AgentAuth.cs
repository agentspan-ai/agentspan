// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Conductor.AI;

/// <summary>
/// Attaches the Agentspan control-plane auth header to every <c>/agent/*</c> request.
///
/// <para>Mirrors the Python/TypeScript SDKs (and the Conductor client's own token
/// flow): an explicit key with no secret is treated as a ready token; a key+secret
/// pair is exchanged for a JWT via <c>POST {server}/token</c>, cached until ~expiry,
/// and sent as <c>X-Authorization</c>. With no credentials, no header is added (OSS
/// anonymous mode). This replaces sending raw <c>X-Auth-Key</c>/<c>X-Auth-Secret</c>,
/// which an Orkes-secured gateway rejects.</para>
/// </summary>
internal sealed class AgentAuthHandler : DelegatingHandler
{
    private readonly string _serverUrl;
    private readonly string? _authKey;
    private readonly string? _authSecret;
    private readonly HttpClient _tokenClient;
    private readonly SemaphoreSlim _lock = new(1, 1);

    private string? _token;
    private long _tokenExpUnix; // 0 = unknown expiry → always refresh

    /// <param name="tokenHandler">Handler for the <c>/token</c> mint call. Tests inject a stub;
    /// production defaults to a fresh <see cref="HttpClientHandler"/> (kept separate from the
    /// outer pipeline so minting never recurses through this handler).</param>
    internal AgentAuthHandler(string serverUrl, string? authKey, string? authSecret,
        HttpMessageHandler? tokenHandler = null)
    {
        _serverUrl   = serverUrl.TrimEnd('/');
        _authKey     = string.IsNullOrEmpty(authKey) ? null : authKey;
        _authSecret  = string.IsNullOrEmpty(authSecret) ? null : authSecret;
        _tokenClient = new HttpClient(tokenHandler ?? new HttpClientHandler())
        {
            Timeout = TimeSpan.FromSeconds(30),
        };
    }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var header = await ResolveAuthHeaderAsync(cancellationToken);
        if (!string.IsNullOrEmpty(header))
        {
            request.Headers.Remove("X-Authorization");
            request.Headers.TryAddWithoutValidation("X-Authorization", header);
        }
        return await base.SendAsync(request, cancellationToken);
    }

    /// <summary>The current auth header value: "" (no creds), the explicit key (token), or a minted JWT.</summary>
    internal async Task<string> ResolveAuthHeaderAsync(CancellationToken ct = default)
    {
        // Explicit key without secret → already a token (mirrors Python's api_key path).
        if (_authKey is not null && _authSecret is null) return _authKey;
        // Need both to mint; otherwise anonymous.
        if (_authKey is null || _authSecret is null) return "";

        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        if (_token is not null && (_tokenExpUnix == 0 ? false : now < _tokenExpUnix - 30))
            return _token;

        await _lock.WaitAsync(ct);
        try
        {
            now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if (_token is not null && _tokenExpUnix != 0 && now < _tokenExpUnix - 30)
                return _token;

            var token = await MintAsync(ct);
            _token        = token;
            _tokenExpUnix = DecodeJwtExp(token) ?? 0;
            return token ?? "";
        }
        finally
        {
            _lock.Release();
        }
    }

    private async Task<string> MintAsync(CancellationToken ct)
    {
        var body = JsonSerializer.Serialize(new { keyId = _authKey, keySecret = _authSecret });
        using var content = new StringContent(body, Encoding.UTF8, "application/json");
        using var resp = await _tokenClient.PostAsync($"{_serverUrl}/token", content, ct);
        resp.EnsureSuccessStatusCode();
        var node = await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
        return node?["token"]?.GetValue<string>() ?? "";
    }

    /// <summary>Decode a JWT's <c>exp</c> (unix seconds) from its payload, or null if absent/unparseable.</summary>
    internal static long? DecodeJwtExp(string? jwt)
    {
        if (string.IsNullOrEmpty(jwt)) return null;
        var parts = jwt.Split('.');
        if (parts.Length < 2) return null;
        try
        {
            var payload = parts[1].Replace('-', '+').Replace('_', '/');
            switch (payload.Length % 4)
            {
                case 2: payload += "=="; break;
                case 3: payload += "=";  break;
            }
            var json = Encoding.UTF8.GetString(Convert.FromBase64String(payload));
            var node = JsonNode.Parse(json);
            var exp  = node?["exp"];
            return exp is not null ? exp.GetValue<long>() : null;
        }
        catch
        {
            return null;
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) { _tokenClient.Dispose(); _lock.Dispose(); }
        base.Dispose(disposing);
    }
}
