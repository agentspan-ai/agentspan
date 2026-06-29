/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

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
        RequestContext ctx = RequestContext.builder()
                .requestId(UUID.randomUUID().toString())
                .userId("alice")
                .createdAt(Instant.now())
                .build();

        RequestContextHolder.set(ctx);

        assertThat(RequestContextHolder.get()).isPresent();
        assertThat(RequestContextHolder.get().get().getUserId()).isEqualTo("alice");
    }

    @Test
    void clear_removesContext() {
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r1")
                .userId("bob")
                .createdAt(Instant.now())
                .build());

        RequestContextHolder.clear();

        assertThat(RequestContextHolder.get()).isEmpty();
    }

    @Test
    void getRequiredUserId_returnsId_whenSet() {
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r1")
                .userId("u1")
                .createdAt(Instant.now())
                .build());

        assertThat(RequestContextHolder.getRequiredUserId()).isEqualTo("u1");
    }

    @Test
    void getRequiredUserId_throws_whenNotSet() {
        assertThatThrownBy(RequestContextHolder::getRequiredUserId)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("No RequestContext");
    }
}
