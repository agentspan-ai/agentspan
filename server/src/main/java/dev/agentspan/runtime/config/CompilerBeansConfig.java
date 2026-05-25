/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import dev.agentspan.runtime.compiler.AgentCompiler;
import dev.agentspan.runtime.compiler.TerminationCompiler;

/**
 * Wires the compiler classes from {@code dev.agentspan:agentspan-compiler} as Spring beans.
 *
 * <p>The compiler module is plain Java (no Spring annotations) so it can be embedded in
 * non-Spring contexts. This configuration restores the {@code @Component}-style behavior
 * the server previously relied on.
 */
@Configuration
public class CompilerBeansConfig {

    @Bean
    public AgentCompiler agentCompiler() {
        return new AgentCompiler();
    }

    @Bean
    public TerminationCompiler terminationCompiler() {
        return new TerminationCompiler();
    }
}
