/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.eval;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.init.DataSourceInitializer;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

/**
 * Initializes eval observability tables on the shared credential DataSource.
 *
 * <p>Reuses the @Primary DataSource created by CredentialDataSourceConfig so
 * all AgentSpan tables live in the same SQLite/PostgreSQL database file.</p>
 */
@Configuration
public class EvalSchemaConfig {

    @Value("${spring.datasource.url:jdbc:sqlite:agent-runtime.db}")
    private String datasourceUrl;

    private boolean isPostgres() {
        return datasourceUrl != null && datasourceUrl.startsWith("jdbc:postgresql");
    }

    @Bean
    public DataSourceInitializer evalSchemaInitializer(DataSource dataSource) {
        String schemaFile = isPostgres() ? "schema-eval-postgres.sql" : "schema-eval.sql";
        DataSourceInitializer initializer = new DataSourceInitializer();
        initializer.setDataSource(dataSource);
        ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
        populator.addScript(new ClassPathResource(schemaFile));
        populator.setContinueOnError(true);
        initializer.setDatabasePopulator(populator);
        return initializer;
    }

    @Bean("evalJdbc")
    public NamedParameterJdbcTemplate evalJdbc(DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
