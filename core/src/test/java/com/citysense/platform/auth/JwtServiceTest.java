package com.citysense.platform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.citysense.common.config.CitySenseProperties;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class JwtServiceTest {

    private static JwtService service(String secret) {
        return new JwtService(new CitySenseProperties(1,
                new CitySenseProperties.Security(secret, 60, "k", "*"), null, null));
    }

    @Test
    void issuedTokenRoundTrips() {
        JwtService jwt = service("test-secret-test-secret-test-secret-123");
        User user = new User("a@b.dev", "hash", "A", Role.ADMIN, "en");
        UUID id = UUID.randomUUID();
        ReflectionTestUtils.setField(user, "id", id);

        AuthUser parsed = jwt.parse(jwt.issue(user)).orElseThrow();
        assertThat(parsed.id()).isEqualTo(id);
        assertThat(parsed.role()).isEqualTo(Role.ADMIN);
        assertThat(parsed.emailVerified()).isFalse();

        user.markEmailVerified();
        assertThat(jwt.parse(jwt.issue(user)).orElseThrow().emailVerified()).isTrue();
    }

    @Test
    void tokenSignedWithAnotherKeyIsRejected() {
        User user = new User("a@b.dev", "hash", "A", Role.CITIZEN, "en");
        ReflectionTestUtils.setField(user, "id", UUID.randomUUID());
        String forged = service("attacker-secret-attacker-secret-attacker").issue(user);
        assertThat(service("test-secret-test-secret-test-secret-123").parse(forged)).isEmpty();
        assertThat(service("test-secret-test-secret-test-secret-123").parse("garbage")).isEmpty();
    }
}
