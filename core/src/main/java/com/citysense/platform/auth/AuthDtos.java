package com.citysense.platform.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public final class AuthDtos {

    private AuthDtos() {}

    public record RegisterRequest(
            @NotBlank @Email String email,
            @NotBlank @Size(min = 8, max = 72) String password,
            @NotBlank @Size(max = 120) String fullName,
            @Pattern(regexp = "^[a-z]{2}(-[A-Z]{2})?$", message = "must be a language code like 'en' or 'hi'") String language) {}

    public record LoginRequest(@NotBlank @Email String email, @NotBlank String password) {}

    public record UserView(UUID id, String email, String fullName, Role role, String language, boolean emailVerified) {
        static UserView of(User u) {
            return new UserView(u.getId(), u.getEmail(), u.getFullName(), u.getRole(), u.getLanguage(),
                    u.isEmailVerified());
        }
    }

    public record OtpSendRequest(@NotBlank @Email String email) {}

    public record OtpVerifyRequest(@NotBlank @Email String email, @NotBlank @Pattern(regexp = "^[0-9]{4,8}$") String code) {}

    public record PasswordResetRequest(
            @NotBlank @Email String email,
            @NotBlank @Pattern(regexp = "^[0-9]{4,8}$") String code,
            @NotBlank @Size(min = 8, max = 72) String newPassword) {}

    /** Tells the client how to render the OTP screen; the code itself is never returned. */
    public record OtpSentResponse(String email, int codeLength, long expiresInSeconds, long resendAfterSeconds) {}

    public record TokenResponse(String accessToken, String tokenType, long expiresIn, UserView user) {}
}
