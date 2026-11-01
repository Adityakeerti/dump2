package com.citysense.platform.auth;

import com.citysense.common.error.ApiException;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.auth.AuthDtos.LoginRequest;
import com.citysense.platform.auth.AuthDtos.RegisterRequest;
import com.citysense.platform.auth.AuthDtos.TokenResponse;
import com.citysense.platform.auth.AuthDtos.UserView;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtService jwt;
    private final AuditService audit;
    private final OtpService otp;

    public AuthService(UserRepository users, PasswordEncoder encoder, JwtService jwt, AuditService audit,
                       OtpService otp) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
        this.audit = audit;
        this.otp = otp;
    }

    /** Self-registration always creates an unverified CITIZEN; admin and crew accounts are provisioned, never self-assigned. */
    @Transactional
    public TokenResponse register(RegisterRequest req) {
        if (users.existsByEmailIgnoreCase(req.email())) {
            throw ApiException.conflict("Email already registered");
        }
        String language = req.language() == null ? "en" : req.language();
        User user = users.save(new User(req.email().toLowerCase(), encoder.encode(req.password()),
                req.fullName(), Role.CITIZEN, language));
        audit.record(user.getEmail(), "USER_REGISTERED", "user", user.getId().toString(), "SUCCESS", Map.of());
        otp.issue(user, OtpPurpose.VERIFY_EMAIL);   // the returned token carries ev=false until the code is verified
        return token(user);
    }

    @Transactional(readOnly = true)
    public TokenResponse login(LoginRequest req) {
        // Same message for unknown email and wrong password, so accounts can't be enumerated.
        User user = users.findByEmailIgnoreCase(req.email())
                .filter(u -> encoder.matches(req.password(), u.getPasswordHash()))
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "Invalid email or password"));
        return token(user);
    }

    @Transactional(readOnly = true)
    public UserView me(AuthUser principal) {
        return users.findById(principal.id()).map(UserView::of)
                .orElseThrow(() -> ApiException.notFound("User", principal.id()));
    }

    private TokenResponse token(User user) {
        return new TokenResponse(jwt.issue(user), "Bearer", jwt.ttlSeconds(), UserView.of(user));
    }
}
