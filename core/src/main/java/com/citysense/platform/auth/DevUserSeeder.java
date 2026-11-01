package com.citysense.platform.auth;

import com.citysense.common.config.CitySenseProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/** Seeds one account per role for local development and demos. Disable with SEED_USERS=false. */
@Component
public class DevUserSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DevUserSeeder.class);

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final CitySenseProperties props;

    public DevUserSeeder(UserRepository users, PasswordEncoder encoder, CitySenseProperties props) {
        this.users = users;
        this.encoder = encoder;
        this.props = props;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!props.seed().enabled()) {
            return;
        }
        seed("admin@citysense.dev", "City Admin", Role.ADMIN);
        seed("crew@citysense.dev", "Ambulance Crew 1", Role.CREW);
        seed("citizen@citysense.dev", "Demo Citizen", Role.CITIZEN);
    }

    private void seed(String email, String name, Role role) {
        if (users.existsByEmailIgnoreCase(email)) {
            return;
        }
        User user = new User(email, encoder.encode(props.seed().defaultPassword()), name, role, "en");
        user.markEmailVerified();   // seeded demo accounts skip the OTP step
        users.save(user);
        log.warn("Seeded dev user {} ({}) with the default seed password - do not use in production", email, role);
    }
}
