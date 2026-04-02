/*
 * Copyright (c) 2025 AgentSpan
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
 * Maps the public URL {@code /docs/} to the static files stored under
 * {@code classpath:/static/api-docs-ui/}. A servlet filter handles the
 * bare {@code /docs} and {@code /docs/} paths before the Conductor SPA
 * interceptor can forward them to the main UI.
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
                ((HttpServletResponse) response).sendRedirect("/docs/");
                return;
            }
            if ("/docs/".equals(uri)) {
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
