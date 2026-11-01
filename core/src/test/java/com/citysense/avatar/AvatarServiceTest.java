package com.citysense.avatar;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.citysense.common.error.ApiException;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.auth.Role;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class AvatarServiceTest {

    @Test
    void unverifiedUsersAreRejected() {
        assertThatThrownBy(() -> AvatarService.requireVerified(
                new AuthUser(UUID.randomUUID(), "a@b", Role.CITIZEN, false)))
                .isInstanceOfSatisfying(ApiException.class,
                        e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> AvatarService.requireVerified(null))
                .isInstanceOfSatisfying(ApiException.class,
                        e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.UNAUTHORIZED));
        assertThatCode(() -> AvatarService.requireVerified(
                new AuthUser(UUID.randomUUID(), "a@b", Role.CITIZEN, true))).doesNotThrowAnyException();
    }

    @Test
    void haversineMatchesKnownDistance() {
        // Clock Tower to Dehradun railway station, roughly 1.3 km apart.
        double d = AvatarService.haversineMeters(30.3243, 78.0418, 30.3155, 78.0331);
        assertThat(d).isBetween(1200.0, 1400.0);
        assertThat(AvatarService.haversineMeters(30, 78, 30, 78)).isZero();
    }
}
