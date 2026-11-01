package com.citysense.platform.auth;

import com.citysense.common.error.ApiException;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.auth.AuthDtos.OtpSentResponse;
import com.citysense.platform.auth.AuthDtos.TokenResponse;
import com.citysense.platform.auth.AuthDtos.UserView;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Email one-time codes for account verification and password reset. Codes are BCrypt-hashed,
 * single-use, bound to one purpose, expire after ttlSeconds and lock after maxAttempts wrong
 * guesses. Send endpoints answer identically whether or not the email is registered.
 */
@Service
public class OtpService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final UserRepository users;
    private final EmailOtpRepository otps;
    private final PasswordEncoder encoder;
    private final OtpMailer mailer;
    private final OtpProperties props;
    private final JwtService jwt;
    private final AuditService audit;

    public OtpService(UserRepository users, EmailOtpRepository otps, PasswordEncoder encoder, OtpMailer mailer,
                      OtpProperties props, JwtService jwt, AuditService audit) {
        this.users = users;
        this.otps = otps;
        this.encoder = encoder;
        this.mailer = mailer;
        this.props = props;
        this.jwt = jwt;
        this.audit = audit;
    }

    /** (Re)sends an email-verification code to an unverified account. */
    @Transactional
    public OtpSentResponse send(String email) {
        return sendIfEligible(email, users.findByEmailIgnoreCase(email).filter(u -> !u.isEmailVerified()),
                OtpPurpose.VERIFY_EMAIL);
    }

    /** Sends a password-reset code to any existing account. */
    @Transactional
    public OtpSentResponse sendPasswordReset(String email) {
        return sendIfEligible(email, users.findByEmailIgnoreCase(email), OtpPurpose.RESET_PASSWORD);
    }

    /** Called on registration, inside the registering transaction. */
    @Transactional
    public void issue(User user, OtpPurpose purpose) {
        otps.findByUserIdAndPurposeAndConsumedAtIsNull(user.getId(), purpose).forEach(EmailOtp::consume);
        String code = generateCode(props.codeLength());
        otps.save(new EmailOtp(user.getId(), purpose, encoder.encode(code),
                Instant.now().plusSeconds(props.ttlSeconds())));
        mailer.send(user.getEmail(), code, purpose);
    }

    // Wrong guesses must persist their attempt count even though the request fails.
    @Transactional(noRollbackFor = ApiException.class)
    public TokenResponse verify(String email, String code) {
        User user = users.findByEmailIgnoreCase(email).orElseThrow(OtpService::invalid);
        if (user.isEmailVerified()) {
            throw ApiException.conflict("Email is already verified; sign in instead");
        }
        redeem(user, OtpPurpose.VERIFY_EMAIL, code);
        user.markEmailVerified();
        users.save(user);
        audit.record(user.getEmail(), "EMAIL_VERIFIED", "user", user.getId().toString(), "SUCCESS", Map.of());
        return token(user);
    }

    @Transactional(noRollbackFor = ApiException.class)
    public TokenResponse resetPassword(String email, String code, String newPassword) {
        User user = users.findByEmailIgnoreCase(email).orElseThrow(OtpService::invalid);
        redeem(user, OtpPurpose.RESET_PASSWORD, code);
        user.changePasswordHash(encoder.encode(newPassword));
        user.markEmailVerified();   // redeeming an emailed code proves ownership of the address
        users.save(user);
        audit.record(user.getEmail(), "PASSWORD_RESET", "user", user.getId().toString(), "SUCCESS", Map.of());
        return token(user);
    }

    private OtpSentResponse sendIfEligible(String email, Optional<User> user, OtpPurpose purpose) {
        long wait = props.resendCooldownSeconds();
        if (user.isPresent()) {
            long remaining = cooldownRemaining(user.get(), purpose);
            if (remaining == 0) {
                issue(user.get(), purpose);
            } else {
                wait = remaining;
            }
        }
        return new OtpSentResponse(email.toLowerCase(), props.codeLength(), props.ttlSeconds(), wait);
    }

    private void redeem(User user, OtpPurpose purpose, String code) {
        EmailOtp otp = otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), purpose)
                .filter(o -> !o.isConsumed() && o.getExpiresAt().isAfter(Instant.now()))
                .orElseThrow(OtpService::invalid);
        if (otp.getAttempts() >= props.maxAttempts()) {
            otp.consume();
            throw new ApiException(HttpStatus.TOO_MANY_REQUESTS, "Too many attempts; request a new code");
        }
        otp.recordAttempt();
        if (!encoder.matches(code, otp.getCodeHash())) {
            int left = props.maxAttempts() - otp.getAttempts();
            throw new ApiException(HttpStatus.BAD_REQUEST, "Incorrect code; " + left + " attempt(s) left");
        }
        otp.consume();
    }

    private TokenResponse token(User user) {
        return new TokenResponse(jwt.issue(user), "Bearer", jwt.ttlSeconds(), UserView.of(user));
    }

    private long cooldownRemaining(User user, OtpPurpose purpose) {
        return otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), purpose)
                .map(o -> props.resendCooldownSeconds()
                        - Duration.between(o.getCreatedAt(), Instant.now()).toSeconds())
                .filter(s -> s > 0)
                .orElse(0L);
    }

    private static ApiException invalid() {
        return new ApiException(HttpStatus.BAD_REQUEST, "Code is invalid or expired; request a new one");
    }

    static String generateCode(int length) {
        StringBuilder sb = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            sb.append(RANDOM.nextInt(10));
        }
        return sb.toString();
    }
}
