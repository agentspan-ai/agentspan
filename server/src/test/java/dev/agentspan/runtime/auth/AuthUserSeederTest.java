package dev.agentspan.runtime.auth;

import static org.mockito.Mockito.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AuthUserSeederTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private AuthProperties authProperties;

    @InjectMocks
    private AuthUserSeeder seeder;

    @Test
    void seed_callsCreateIfNotExists_forEachConfiguredUser() {
        AuthProperties.UserEntry entry1 = new AuthProperties.UserEntry();
        entry1.setUsername("alice");
        entry1.setPassword("secret");
        AuthProperties.UserEntry entry2 = new AuthProperties.UserEntry();
        entry2.setUsername("bob");
        entry2.setPassword("pass2");

        when(authProperties.getUsers()).thenReturn(List.of(entry1, entry2));

        seeder.seed();

        verify(userRepository).createIfNotExists("alice", "alice", null, "secret");
        verify(userRepository).createIfNotExists("bob", "bob", null, "pass2");
    }

    @Test
    void seed_withNoConfiguredUsers_doesNothing() {
        when(authProperties.getUsers()).thenReturn(List.of());
        seeder.seed();
        verifyNoInteractions(userRepository);
    }
}
