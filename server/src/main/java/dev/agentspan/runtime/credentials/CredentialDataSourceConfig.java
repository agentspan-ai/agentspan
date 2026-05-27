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
 * <p>SQLite: maximumPoolSize=8. WAL mode (enabled via the JDBC URL) supports
 * concurrent readers and a single writer; HikariCP serializes writes at the
 * pool level when contention is rare, and busy_timeout=15000 absorbs the
 * occasional write conflict. The previous cap of 1 was a conservative legacy
 * setting that serialized all reads — under PAC/PAE workloads (planner +
 * parallel generate-block LLM calls, each resolving credentials), a single
 * connection caused pool exhaustion (waiting=39, timeout=30s). minimumIdle=1
 * keeps the connection alive for in-memory shared-cache DBs.</p>
 *
 * <p>PostgreSQL: uses {@code org.postgresql.Driver} with a larger pool (default 8).</p>
 */
@Configuration
public class CredentialDataSourceConfig {

    private static final Logger log = LoggerFactory.getLogger(CredentialDataSourceConfig.class);

    private static final int POSTGRES_POOL_SIZE = 8;
    private static final int SQLITE_POOL_SIZE = 8;

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
            // SQLite WAL mode supports concurrent readers and one writer. The
            // pool of 8 lets credential reads run in parallel (the hot path
            // for AgentspanAIModelProvider's per-LLM-call credential
            // resolution). busy_timeout below absorbs write contention.
            config.setMaximumPoolSize(SQLITE_POOL_SIZE);
            config.setMinimumIdle(1);
            config.setConnectionTestQuery("SELECT 1");
            // busy_timeout: wait up to 15s when another connection holds a write lock.
            // The production URL sets this via ?busy_timeout=15000, but the test URL uses
            // SQLite's file: URI syntax (?mode=memory&cache=shared) where JDBC-level
            // parameters are not parsed, so the PRAGMA never gets applied from the URL.
            // connectionInitSql ensures it is set uniformly in all environments.
            config.setConnectionInitSql("PRAGMA busy_timeout = 15000");
        }

        log.info(
                "Credential DataSource (HikariCP/{}) initialized: {}", postgres ? "postgres" : "sqlite", datasourceUrl);
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
        String schemaFile = isPostgres() ? "schema-credentials-postgres.sql" : "schema-credentials.sql";

        DataSourceInitializer initializer = new DataSourceInitializer();
        initializer.setDataSource(dataSource);
        ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
        populator.addScript(new ClassPathResource(schemaFile));
        populator.setContinueOnError(true); // IF NOT EXISTS guards handle re-runs
        initializer.setDatabasePopulator(populator);
        return initializer;
    }
}
