/**
 * Base error for all Agentspan SDK errors.
 */
export class AgentspanError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AgentspanError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * HTTP API error with status code and response body.
 */
export class AgentAPIError extends AgentspanError {
  readonly statusCode: number;
  readonly responseBody: string;

  constructor(message: string, statusCode: number, responseBody: string) {
    super(message);
    this.name = 'AgentAPIError';
    this.statusCode = statusCode;
    this.responseBody = responseBody;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Agent not found by name.
 */
export class AgentNotFoundError extends AgentspanError {
  readonly agentName: string;

  constructor(agentName: string) {
    super(`Agent not found: ${agentName}`);
    this.name = 'AgentNotFoundError';
    this.agentName = agentName;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Configuration error — invalid or missing config values.
 */
export class ConfigurationError extends AgentspanError {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigurationError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Credential not found in the credential store.
 */
export class CredentialNotFoundError extends AgentspanError {
  readonly credentialName: string;

  constructor(credentialName: string) {
    super(`Credential not found: ${credentialName}`);
    this.name = 'CredentialNotFoundError';
    this.credentialName = credentialName;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Credential authentication error — execution token invalid or expired.
 */
export class CredentialAuthError extends AgentspanError {
  constructor(message: string = 'Credential authentication failed') {
    super(message);
    this.name = 'CredentialAuthError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Credential rate limit exceeded (120 calls/min).
 */
export class CredentialRateLimitError extends AgentspanError {
  constructor(message: string = 'Credential rate limit exceeded') {
    super(message);
    this.name = 'CredentialRateLimitError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Credential service error — server-side failure.
 */
export class CredentialServiceError extends AgentspanError {
  constructor(message: string = 'Credential service error') {
    super(message);
    this.name = 'CredentialServiceError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * SSE connection timeout — no events received within the timeout window.
 */
export class SSETimeoutError extends AgentspanError {
  constructor(message: string = 'SSE connection timed out') {
    super(message);
    this.name = 'SSETimeoutError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Terminal tool error — non-retryable failure (e.g., CLI command exited non-zero).
 * Causes the Conductor task to be marked FAILED_WITH_TERMINAL_ERROR.
 */
export class TerminalToolError extends AgentspanError {
  constructor(message: string) {
    super(message);
    this.name = 'TerminalToolError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Guardrail validation failed.
 */
export class GuardrailFailedError extends AgentspanError {
  readonly guardrailName: string;
  readonly failureMessage: string;

  constructor(guardrailName: string, failureMessage: string) {
    super(`Guardrail '${guardrailName}' failed: ${failureMessage}`);
    this.name = 'GuardrailFailedError';
    this.guardrailName = guardrailName;
    this.failureMessage = failureMessage;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
