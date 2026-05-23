/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import org.junit.jupiter.api.Test;

class AgentspanAIModelProviderTest {

    @Test
    void openAIConfigurationSetsHttpClientRequiredByConductorAi() {
        var config = AgentspanAIModelProvider.openAIConfiguration("test-key", "https://api.openai.com/v1");

        assertThat(config.getConductorAiHttpClient()).isNotNull();
        assertThatCode(config::get).doesNotThrowAnyException();
    }
}
