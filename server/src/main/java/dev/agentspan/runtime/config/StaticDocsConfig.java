/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.config;

import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Serves the standalone API docs bundle at {@code /docs/} and its assets,
 * and ensures hard-refreshing {@code /docs} serves the main SPA so React
 * Router renders the embedded API docs page inside the app shell.
 *
 * <p>URL routing:
 * <ul>
 *   <li>{@code /docs}   → forward to main SPA ({@code /index.html}); React Router
 *       renders ApiDocsPage embedded inside the app shell (no redirect).</li>
 *   <li>{@code /docs/}  → forward to standalone docs ({@code /docs/index.html});
 *       preserved as a direct/shareable full-page docs URL.</li>
 *   <li>{@code /docs/**} → static assets for the standalone docs bundle
 *       (JS, CSS served from {@code classpath:/static/docs/}).</li>
 * </ul>
 */
@Configuration
public class StaticDocsConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**").addResourceLocations("classpath:/static/docs/");
    }

    @Bean
    public FilterRegistrationBean<Filter> docsFilter() {
        FilterRegistrationBean<Filter> reg = new FilterRegistrationBean<>();
        reg.setFilter((request, response, chain) -> {
            HttpServletRequest req = (HttpServletRequest) request;
            String uri = req.getRequestURI();
            if ("/docs".equals(uri)) {
                // Hard-refresh on /docs: serve the main SPA so React Router
                // picks up the /docs route and renders the embedded docs page.
                request.getRequestDispatcher("/index.html").forward(request, response);
                return;
            }
            if ("/docs/".equals(uri)) {
                // Direct link to the standalone full-page docs view.
                request.getRequestDispatcher("/docs/index.html").forward(request, response);
                return;
            }
            chain.doFilter(request, response);
        });
        reg.addUrlPatterns("/docs", "/docs/");
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return reg;
    }
}
