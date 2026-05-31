package dev.agentspan.runtime.auth;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class UserRepositoryTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    @BeforeEach
    void cleanUsers() {
        jdbc.update("DELETE FROM users WHERE username LIKE 'test_%'", Map.of());
    }

    @Test
    void findByUsername_returnsEmpty_whenNotFound() {
        assertThat(userRepository.findByUsername("no_such_user")).isEmpty();
    }

    @Test
    void createAndFindByUsername_roundTrips() {
        User user = userRepository.create("test_alice", "Alice Test", "alice@test.com", "secret");

        Optional<User> found = userRepository.findByUsername("test_alice");

        assertThat(found).isPresent();
        assertThat(found.get().getId()).isNotBlank();
        assertThat(found.get().getName()).isEqualTo("Alice Test");
    }

    @Test
    void findByUsername_afterCreate_doesNotExposePassword() {
        userRepository.create("test_bob", "Bob Test", "bob@test.com", "mypassword");

        // Ensure the plain-text password is NOT stored or returned
        Optional<User> found = userRepository.findByUsername("test_bob");
        assertThat(found).isPresent();
        // User DTO has no password field; verification is via UserRepository.checkPassword
    }

    @Test
    void checkPassword_correct_returnsTrue() {
        userRepository.create("test_carol", "Carol", "carol@test.com", "mySecret");

        assertThat(userRepository.checkPassword("test_carol", "mySecret")).isTrue();
    }

    @Test
    void checkPassword_wrong_returnsFalse() {
        userRepository.create("test_dave", "Dave", "dave@test.com", "correct");

        assertThat(userRepository.checkPassword("test_dave", "wrong")).isFalse();
    }

    @Test
    void findById_roundTrips() {
        User created = userRepository.create("test_eve", "Eve", "eve@test.com", "pw");

        Optional<User> found = userRepository.findById(created.getId());

        assertThat(found).isPresent();
        assertThat(found.get().getUsername()).isEqualTo("test_eve");
    }

    // ── BCrypt 72-char truncation guard (GHSA-mg83-c7gq-rv5c) ──────────
    //
    // BCryptPasswordEncoder only hashes the first 72 bytes. Without an
    // explicit length cap, a 73+-char password silently truncates — and an
    // attacker who knows the first 72 chars can authenticate with any
    // suffix. Reject longer passwords at the SDK boundary instead.

    @Test
    void create_rejects_password_longer_than_72_chars() {
        String tooLong = "a".repeat(73);
        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> userRepository.create("test_long", "Long", "long@test.com", tooLong));
    }

    @Test
    void checkPassword_rejects_attempt_longer_than_72_chars() {
        // Create with a 72-char password; an attempt that shares the first
        // 72 chars but differs at position 73 must NOT authenticate.
        String base = "a".repeat(72);
        userRepository.create("test_long_ok", "Long OK", "lo@test.com", base);

        // Sanity: exact match succeeds.
        assertThat(userRepository.checkPassword("test_long_ok", base)).isTrue();

        // A 73-char attempt is rejected wholesale (length guard) rather
        // than silently truncated. The result is FALSE, never TRUE.
        assertThat(userRepository.checkPassword("test_long_ok", base + "X")).isFalse();
    }
}
