// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.exceptions;

/**
 * Thrown when the Agentspan server returns a non-2xx HTTP response.
 */
public class AgentAPIException extends AgentspanException {
    private final int statusCode;
    private final String responseBody;

    public AgentAPIException(int statusCode, String responseBody) {
        super("API error " + statusCode + ": " + responseBody);
        this.statusCode = statusCode;
        this.responseBody = responseBody;
    }

    public int getStatusCode() {
        return statusCode;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
