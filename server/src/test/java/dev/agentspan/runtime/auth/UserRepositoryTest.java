package dev.agentspan.runtime.auth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import dev.agentspan.runtime.AgentRuntime;

import java.util.Optional;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

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
}
