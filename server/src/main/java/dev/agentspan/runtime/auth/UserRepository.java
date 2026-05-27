/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Repository;

/**
 * Spring JDBC repository for the users table.
 * Passwords are stored as bcrypt hashes — plain text is never persisted.
 */
@Repository
public class UserRepository {

    private static final BCryptPasswordEncoder BCRYPT = new BCryptPasswordEncoder();

    // BCrypt hashes only the first 72 bytes of the input (GHSA-mg83-c7gq-rv5c).
    // Reject longer inputs at this boundary so that two passwords sharing
    // their first 72 chars but differing in the tail never collide.
    private static final int MAX_PASSWORD_LENGTH = 72;

    private final NamedParameterJdbcTemplate jdbc;

    public UserRepository(@Qualifier("credentialJdbc") NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static void requireValidPasswordLength(String raw) {
        if (raw != null && raw.length() > MAX_PASSWORD_LENGTH) {
            throw new IllegalArgumentException(
                    "Password exceeds maximum length of " + MAX_PASSWORD_LENGTH + " characters");
        }
    }

    public Optional<User> findByUsername(String username) {
        try {
            User user = jdbc.queryForObject(
                    "SELECT id, name, email, username FROM users WHERE username = :u",
                    Map.of("u", username),
                    (rs, row) -> new User(
                            rs.getString("id"), rs.getString("name"), rs.getString("email"), rs.getString("username")));
            return Optional.ofNullable(user);
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    public Optional<User> findById(String id) {
        try {
            User user = jdbc.queryForObject(
                    "SELECT id, name, email, username FROM users WHERE id = :id",
                    Map.of("id", id),
                    (rs, row) -> new User(
                            rs.getString("id"), rs.getString("name"), rs.getString("email"), rs.getString("username")));
            return Optional.ofNullable(user);
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    /**
     * Create a new user with a bcrypt-hashed password.
     * Returns the created User (password hash never in User DTO).
     */
    public User create(String username, String name, String email, String plainPassword) {
        requireValidPasswordLength(plainPassword);
        String id = UUID.randomUUID().toString();
        String hash = plainPassword != null ? BCRYPT.encode(plainPassword) : null;
        String now = Instant.now().toString();
        jdbc.update(
                "INSERT INTO users (id, name, email, username, password_hash, created_at) "
                        + "VALUES (:id, :name, :email, :u, :hash, :now)",
                Map.of(
                        "id",
                        id,
                        "name",
                        name,
                        "email",
                        email != null ? email : "",
                        "u",
                        username,
                        "hash",
                        hash != null ? hash : "",
                        "now",
                        now));
        return new User(id, name, email, username);
    }

    /**
     * Verify a username/password pair against the stored bcrypt hash.
     * Returns false if user not found, or password does not match.
     */
    public boolean checkPassword(String username, String plainPassword) {
        // Reject over-length attempts before hashing so we don't leak the
        // first-72-byte truncation behaviour of BCrypt to attackers.
        if (plainPassword != null && plainPassword.length() > MAX_PASSWORD_LENGTH) {
            return false;
        }
        try {
            String hash = jdbc.queryForObject(
                    "SELECT password_hash FROM users WHERE username = :u", Map.of("u", username), String.class);
            return hash != null && BCRYPT.matches(plainPassword, hash);
        } catch (EmptyResultDataAccessException e) {
            return false;
        }
    }

    /**
     * Upsert: create user if not exists (used for config-seeding).
     * Never updates an existing password to avoid overwriting user-changed passwords.
     */
    public void createIfNotExists(String username, String name, String email, String plainPassword) {
        if (findByUsername(username).isEmpty()) {
            create(username, name, email, plainPassword);
        }
    }
}
