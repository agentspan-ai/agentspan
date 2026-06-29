/*
 * Copyright (c) 2026 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.config;

import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Serves the React SPA under the {@code /ui/} context root.
 *
 * <ul>
 *   <li>{@code /}        → 302 redirect to {@code /ui/}</li>
 *   <li>{@code /ui/}     → serves {@code /ui/index.html} (SPA entry point)</li>
 *   <li>{@code /ui/**}   → static assets first; unknown paths fall through to
 *                           {@code /ui/index.html} so React Router handles them</li>
 *   <li>{@code /api/**}  → untouched (Conductor + agentspan REST)</li>
 * </ul>
 */
@Configuration
public class UiRoutingConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/ui/**").addResourceLocations("classpath:/static/");
    }

    @Bean
    public FilterRegistrationBean<Filter> uiRoutingFilter() {
        FilterRegistrationBean<Filter> reg = new FilterRegistrationBean<>();

        reg.setFilter((request, response, chain) -> {
            HttpServletRequest req = (HttpServletRequest) request;
            HttpServletResponse res = (HttpServletResponse) response;
            String uri = req.getRequestURI();

            // Redirect bare root to /ui/
            if ("/".equals(uri)) {
                res.sendRedirect("/ui/");
                return;
            }

            // For any /ui/* path that isn't a real static asset
            // (no dot-extension in the last segment), forward to the SPA
            // so React Router can handle deep links / hard refreshes.
            if (uri.startsWith("/ui/")) {
                String lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
                boolean hasExtension = lastSegment.contains(".");
                if (!hasExtension) {
                    request.getRequestDispatcher("/ui/index.html").forward(request, response);
                    return;
                }
            }

            chain.doFilter(request, response);
        });

        reg.addUrlPatterns("/", "/ui/*");
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 1); // just after docsFilter
        return reg;
    }
}
