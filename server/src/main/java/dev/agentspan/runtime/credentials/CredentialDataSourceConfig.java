/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.init.DataSourceInitializer;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.core.io.ClassPathResource;

import javax.sql.DataSource;

/**
 * Creates a dedicated DataSource for credential tables.
 * Shares the same JDBC URL as Conductor but is a separate connection pool,
 * avoiding conflicts with Conductor's internal DataSource management.
 *
 * <p>Spring's spring.sql.init.mode=always is tied to the primary DataSource.
 * We use a DataSourceInitializer bean instead to explicitly run schema-credentials.sql.</p>
 *
 * <p>Note: We mark credentialDataSource as @Primary to resolve the DataSource ambiguity
 * when multiple beans of type DataSource exist (Conductor also creates "dataSource").
 * Since both use the same JDBC URL, Conductor's Flyway migration runs correctly
 * on our bean. The credential schema initializer also runs on the same bean,
 * so all tables end up in the same database.</p>
 *
 * <p>We use HikariCP with minimumIdle=1 to keep at least one connection alive.
 * This is required for in-memory SQLite databases (shared-cache mode) so that
 * the database is not dropped between the schema initializer and the first query.
 * SQLite does not support concurrent writers, so maximumPoolSize=1.</p>
 */
@Configuration
public class CredentialDataSourceConfig {

    private static final Logger log = LoggerFactory.getLogger(CredentialDataSourceConfig.class);

    @Value("${spring.datasource.url:jdbc:sqlite:agent-runtime.db}")
    private String datasourceUrl;

    @Bean("credentialDataSource")
    @Primary
    public DataSource credentialDataSource() {
        HikariConfig config = new HikariConfig();
        config.setDriverClassName("org.sqlite.JDBC");
        config.setJdbcUrl(datasourceUrl);
        config.setPoolName("credential-pool");
        // SQLite does not support concurrent writers; cap at 1 connection
        config.setMaximumPoolSize(1);
        // Keep at least 1 connection alive — required for in-memory SQLite
        // shared-cache databases so they are not dropped between operations
        config.setMinimumIdle(1);
        config.setConnectionTestQuery("SELECT 1");
        log.info("Credential DataSource (HikariCP) initialized: {}", datasourceUrl);
        return new HikariDataSource(config);
    }

    @Bean("credentialJdbc")
    public NamedParameterJdbcTemplate credentialJdbc() {
        return new NamedParameterJdbcTemplate(credentialDataSource());
    }

    @Bean
    public DataSourceInitializer credentialSchemaInitializer() {
        DataSourceInitializer initializer = new DataSourceInitializer();
        initializer.setDataSource(credentialDataSource());
        ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
        populator.addScript(new ClassPathResource("schema-credentials.sql"));
        populator.setContinueOnError(true); // IF NOT EXISTS guards handle re-runs
        initializer.setDatabasePopulator(populator);
        return initializer;
    }
}
