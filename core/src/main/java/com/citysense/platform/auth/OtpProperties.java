package com.citysense.platform.auth;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Email OTP policy. {@code logFallback} prints codes to the server log when no SMTP server is
 * configured (spring.mail.host unset) - local development only; disable it anywhere real.
 */
@ConfigurationProperties(prefix = "citysense.otp")
public record OtpProperties(
        int codeLength,
        long ttlSeconds,
        int maxAttempts,
        long resendCooldownSeconds,
        String mailFrom,
        String mailSubject,
        boolean logFallback) {}
