/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

/** Validates stored credential values before they are reused in HTTP headers. */
public final class CredentialValueValidator {

    private CredentialValueValidator() {}

    public static void validate(String name, String value) {
        if (value == null) {
            throw new InvalidCredentialValueException(name, "value is required");
        }
        if (!value.equals(value.strip())) {
            throw new InvalidCredentialValueException(
                    name,
                    "contains leading or trailing whitespace. Re-enter the value on one line without surrounding spaces.");
        }
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (ch == '\n') {
                throw invalidChar(name, "newline");
            }
            if (ch == '\r') {
                throw invalidChar(name, "carriage return");
            }
            if (ch == '\t') {
                throw invalidChar(name, "tab");
            }
            if (Character.isISOControl(ch)) {
                throw invalidChar(name, String.format("control character 0x%02x", (int) ch));
            }
        }
    }

    private static InvalidCredentialValueException invalidChar(String name, String charName) {
        return new InvalidCredentialValueException(
                name,
                "contains a " + charName + ". This usually means the value was wrapped or pasted with extra whitespace; "
                        + "re-export it on a single line and store it again.");
    }

    public static class InvalidCredentialValueException extends RuntimeException {
        public InvalidCredentialValueException(String name, String reason) {
            super("Credential '" + name + "' " + reason);
        }
    }
}
