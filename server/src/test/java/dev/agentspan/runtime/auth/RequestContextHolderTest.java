package dev.agentspan.runtime.auth;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class RequestContextHolderTest {

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void getContext_returnsEmpty_whenNotSet() {
        assertThat(RequestContextHolder.get()).isEmpty();
    }

    @Test
    void setAndGet_roundTrips() {
        User user = new User(UUID.randomUUID().toString(), "Alice", "alice@test.com", "alice");
        RequestContext ctx = RequestContext.builder()
            .requestId(UUID.randomUUID().toString())
            .user(user)
            .createdAt(Instant.now())
            .build();

        RequestContextHolder.set(ctx);

        assertThat(RequestContextHolder.get()).isPresent();
        assertThat(RequestContextHolder.get().get().getUser().getUsername()).isEqualTo("alice");
    }

    @Test
    void clear_removesContext() {
        User user = new User(UUID.randomUUID().toString(), "Bob", "bob@test.com", "bob");
        RequestContextHolder.set(RequestContext.builder()
            .requestId("r1").user(user).createdAt(Instant.now()).build());

        RequestContextHolder.clear();

        assertThat(RequestContextHolder.get()).isEmpty();
    }

    @Test
    void getRequiredUser_returnsUser_whenSet() {
        User user = new User("u1", "Carol", "carol@test.com", "carol");
        RequestContextHolder.set(RequestContext.builder()
            .requestId("r1").user(user).createdAt(Instant.now()).build());

        User result = RequestContextHolder.getRequiredUser();
        assertThat(result.getId()).isEqualTo("u1");
    }

    @Test
    void getRequiredUser_throws_whenNotSet() {
        org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> RequestContextHolder.getRequiredUser())
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("No RequestContext");
    }
}
