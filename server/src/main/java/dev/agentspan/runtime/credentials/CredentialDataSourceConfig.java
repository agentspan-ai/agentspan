/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import javax.sql.DataSource;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.init.DataSourceInitializer;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

/**
 * Creates a dedicated DataSource for credential tables.
 * Shares the same JDBC URL as Conductor but is a separate connection pool,
 * avoiding conflicts with Conductor's internal DataSource management.
 *
 * <p>Spring's spring.sql.init.mode=always is tied to the primary DataSource.
 * We use a DataSourceInitializer bean instead to explicitly run the credential schema.</p>
 *
 * <p>Note: We mark credentialDataSource as @Primary to resolve the DataSource ambiguity
 * when multiple beans of type DataSource exist (Conductor also creates "dataSource").
 * Since both use the same JDBC URL, Conductor's Flyway migration runs correctly
 * on our bean. The credential schema initializer also runs on the same bean,
 * so all tables end up in the same database.</p>
 *
 * <p>Supports both SQLite (default profile) and PostgreSQL (postgres profile).
 * The driver class and connection pool size are derived automatically from the
 * {@code spring.datasource.url} value — no extra configuration is required.</p>
 *
 * <p>SQLite: maximumPoolSize=1 (no concurrent writers). In-memory SQLite also
 * requires minimumIdle=1 so the database is not dropped between operations.</p>
 *
 * <p>PostgreSQL: uses {@code org.postgresql.Driver} with a larger pool (default 8).</p>
 */
@Configuration
public class CredentialDataSourceConfig {

    private static final Logger log = LoggerFactory.getLogger(CredentialDataSourceConfig.class);

    private static final int POSTGRES_POOL_SIZE = 8;

    @Value("${spring.datasource.url:jdbc:sqlite:agent-runtime.db}")
    private String datasourceUrl;

    @Value("${spring.datasource.username:}")
    private String datasourceUsername;

    @Value("${spring.datasource.password:}")
    private String datasourcePassword;

    /** Returns {@code true} when the configured JDBC URL targets PostgreSQL. */
    private boolean isPostgres() {
        return datasourceUrl != null && datasourceUrl.startsWith("jdbc:postgresql");
    }

    @Bean("credentialDataSource")
    @Primary
    public DataSource credentialDataSource() {
        boolean postgres = isPostgres();
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(datasourceUrl);
        config.setPoolName("credential-pool");

        if (postgres) {
            config.setDriverClassName("org.postgresql.Driver");
            config.setMaximumPoolSize(POSTGRES_POOL_SIZE);
            config.setMinimumIdle(1);
            if (!datasourceUsername.isEmpty()) config.setUsername(datasourceUsername);
            if (!datasourcePassword.isEmpty()) config.setPassword(datasourcePassword);
        } else {
            config.setDriverClassName("org.sqlite.JDBC");
            // SQLite does not support concurrent writers; cap at 1 connection.
            // minimumIdle=1 keeps the connection alive for in-memory shared-cache DBs.
            config.setMaximumPoolSize(1);
            config.setMinimumIdle(1);
            config.setConnectionTestQuery("SELECT 1");
        }

        log.info("Credential DataSource (HikariCP/{}) initialized: {}",
                postgres ? "postgres" : "sqlite", datasourceUrl);
        return new HikariDataSource(config);
    }

    @Bean("credentialJdbc")
    public NamedParameterJdbcTemplate credentialJdbc(
            @org.springframework.beans.factory.annotation.Qualifier("credentialDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    public DataSourceInitializer credentialSchemaInitializer(
            @org.springframework.beans.factory.annotation.Qualifier("credentialDataSource") DataSource dataSource) {
        // Use a database-specific DDL file so that column types are correct:
        //   SQLite  → schema-credentials.sql          (BLOB for binary data)
        //   Postgres → schema-credentials-postgres.sql (BYTEA for binary data)
        String schemaFile = isPostgres()
                ? "schema-credentials-postgres.sql"
                : "schema-credentials.sql";

        DataSourceInitializer initializer = new DataSourceInitializer();
        initializer.setDataSource(dataSource);
        ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
        populator.addScript(new ClassPathResource(schemaFile));
        populator.setContinueOnError(true); // IF NOT EXISTS guards handle re-runs
        initializer.setDatabasePopulator(populator);
        return initializer;
    }
}
