/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.config;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.FilterType;

/**
 * Registers the AgentSpan beans by component-scanning the {@code dev.agentspan.runtime}
 * namespace — agent domain, compilers, services, controllers, system tasks, and whichever
 * SPI implementations are present on the classpath.
 *
 * <p>Loaded via {@code META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports},
 * so an embedding host (e.g. orkes-conductor) gets the beans without adding
 * {@code dev.agentspan} to its own component scan. The standalone server's main class
 * ({@code AgentRuntime}) scans only the Conductor packages and relies on this
 * auto-configuration for the AgentSpan beans.
 *
 * <p><b>Activation contract.</b> Merely having this library on the classpath must not change a
 * host application's behavior. The configuration activates only when:
 * <ul>
 *   <li><b>Standalone:</b> the standalone server distribution is the application — detected by its
 *       entry point ({@code dev.agentspan.runtime.AgentRuntime}, shipped only in
 *       {@code conductor-agentspan-server}) being on the classpath; or</li>
 *   <li><b>Embedded:</b> the host explicitly opts in with {@code agentspan.embedded=true}
 *       (e.g. orkes-conductor). Without the flag, the host runs as stock Conductor — no
 *       AgentSpan beans, controllers, or system-task overrides are registered.</li>
 * </ul>
 *
 * <p>The scan spans both jars (library + server) because they share the
 * {@code dev.agentspan.runtime} namespace: the library's contracts and logic are always
 * present, while the server's default SPI implementations and web config are present only
 * in the standalone distribution. An embedding host supplies its own SPI implementations.
 *
 * <p>Excludes the standalone entry point ({@code dev.agentspan.runtime.AgentRuntime}) and
 * this class, which are processed directly rather than via the scan.
 */
@AutoConfiguration
@Conditional(AgentSpanAutoConfiguration.StandaloneOrExplicitlyEmbedded.class)
@ComponentScan(
        basePackages = "dev.agentspan.runtime",
        excludeFilters = {
            @ComponentScan.Filter(type = FilterType.REGEX, pattern = "dev\\.agentspan\\.runtime\\.AgentRuntime"),
            @ComponentScan.Filter(
                    type = FilterType.REGEX,
                    pattern = "dev\\.agentspan\\.runtime\\.config\\.AgentSpanAutoConfiguration")
        })
public class AgentSpanAutoConfiguration {

    /**
     * Activate when running as the standalone AgentSpan server (its entry point class is on the
     * classpath) OR when an embedding host explicitly sets {@code agentspan.embedded=true}.
     */
    static class StandaloneOrExplicitlyEmbedded extends AnyNestedCondition {

        StandaloneOrExplicitlyEmbedded() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnClass(name = "dev.agentspan.runtime.AgentRuntime")
        static class StandaloneServer {}

        @ConditionalOnProperty(name = "agentspan.embedded", havingValue = "true")
        static class HostOptedIn {}
    }
}
