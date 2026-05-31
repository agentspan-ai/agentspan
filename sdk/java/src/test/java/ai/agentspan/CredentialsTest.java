// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import static org.junit.jupiter.api.Assertions.*;

import ai.agentspan.exceptions.CredentialNotFoundException;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for the {@link Credentials} thread-local accessor.
 *
 * <p>Java is tier-1-only per the SDK secret-injection contract; this is the
 * only injection mechanism. Tests cover:</p>
 * <ul>
 *   <li>Reading a set value via {@link Credentials#get(String)}.</li>
 *   <li>Missing context → typed exception (not silent null).</li>
 *   <li>Per-thread isolation — concurrent threads see independent contexts.</li>
 *   <li>{@code clearForCall} cleanly removes the ThreadLocal.</li>
 * </ul>
 */
class CredentialsTest {

    @AfterEach
    void cleanUp() {
        Credentials.clearForCall();
    }

    @Test
    void get_returnsSetValue() {
        Credentials.setForCall(Map.of("OPENAI_API_KEY", "sk-test-123"));
        assertEquals("sk-test-123", Credentials.get("OPENAI_API_KEY"));
    }

    @Test
    void get_outsideToolCall_throwsCredentialNotFound() {
        Credentials.clearForCall();
        CredentialNotFoundException ex = assertThrows(
                CredentialNotFoundException.class, () -> Credentials.get("ANYTHING"));
        assertTrue(ex.getMessage().contains("outside a credential-aware"),
                "message should explain why no context: " + ex.getMessage());
    }

    @Test
    void get_unknownName_throwsCredentialNotFound() {
        Credentials.setForCall(Map.of("KNOWN", "value"));
        assertThrows(CredentialNotFoundException.class, () -> Credentials.get("UNKNOWN"));
    }

    @Test
    void getOrNull_returnsNullSilentlyOutsideContext() {
        Credentials.clearForCall();
        assertNull(Credentials.getOrNull("ANY"));
    }

    @Test
    void all_returnsUnmodifiableViewOfCurrentContext() {
        Credentials.setForCall(Map.of("A", "1", "B", "2"));
        Map<String, String> view = Credentials.all();
        assertEquals(2, view.size());
        assertEquals("1", view.get("A"));
        assertThrows(UnsupportedOperationException.class, () -> view.put("C", "3"));
    }

    @Test
    void perThreadIsolation_concurrentThreadsDontShareContext() throws Exception {
        // Audit-style: two threads each set a different value for the same key,
        // both read back inside their own thread. Neither should observe the
        // other's value. Mirrors Python's contextvars-isolation test and TS's
        // runWithCredentialContext isolation test.
        AtomicReference<String> threadAObserved = new AtomicReference<>();
        AtomicReference<String> threadBObserved = new AtomicReference<>();
        CountDownLatch bothSet = new CountDownLatch(2);
        CountDownLatch bothRead = new CountDownLatch(2);

        Runnable threadA = () -> {
            try {
                Credentials.setForCall(Map.of("KEY", "value-A"));
                bothSet.countDown();
                bothSet.await(5, TimeUnit.SECONDS);  // wait for B to also have set
                threadAObserved.set(Credentials.get("KEY"));
                bothRead.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                Credentials.clearForCall();
            }
        };

        Runnable threadB = () -> {
            try {
                Credentials.setForCall(Map.of("KEY", "value-B"));
                bothSet.countDown();
                bothSet.await(5, TimeUnit.SECONDS);
                threadBObserved.set(Credentials.get("KEY"));
                bothRead.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                Credentials.clearForCall();
            }
        };

        Thread tA = new Thread(threadA, "test-A");
        Thread tB = new Thread(threadB, "test-B");
        tA.start();
        tB.start();
        assertTrue(bothRead.await(10, TimeUnit.SECONDS), "both threads must finish reading");
        tA.join(1000);
        tB.join(1000);

        // ThreadLocal isolates: each thread sees only its own value.
        assertEquals("value-A", threadAObserved.get());
        assertEquals("value-B", threadBObserved.get());
    }

    @Test
    void setForCall_withEmptyMap_clearsContext() {
        Credentials.setForCall(Map.of("X", "y"));
        Credentials.setForCall(Map.of());
        assertNull(Credentials.getOrNull("X"));
    }

    @Test
    void setForCall_withNull_clearsContext() {
        Credentials.setForCall(Map.of("X", "y"));
        Credentials.setForCall(null);
        assertNull(Credentials.getOrNull("X"));
    }
}
