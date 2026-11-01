package com.citysense.platform.auth;

import com.citysense.platform.auth.AuthDtos.LoginRequest;
import com.citysense.platform.auth.AuthDtos.OtpSendRequest;
import com.citysense.platform.auth.AuthDtos.OtpSentResponse;
import com.citysense.platform.auth.AuthDtos.OtpVerifyRequest;
import com.citysense.platform.auth.AuthDtos.PasswordResetRequest;
import com.citysense.platform.auth.AuthDtos.RegisterRequest;
import com.citysense.platform.auth.AuthDtos.TokenResponse;
import com.citysense.platform.auth.AuthDtos.UserView;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
@Tag(name = "Auth")
public class AuthController {

    private final AuthService authService;
    private final OtpService otpService;

    public AuthController(AuthService authService, OtpService otpService) {
        this.authService = authService;
        this.otpService = otpService;
    }

    @PostMapping("/otp/send")
    public OtpSentResponse sendOtp(@Valid @RequestBody OtpSendRequest req) {
        return otpService.send(req.email());
    }

    @PostMapping("/otp/verify")
    public TokenResponse verifyOtp(@Valid @RequestBody OtpVerifyRequest req) {
        return otpService.verify(req.email(), req.code());
    }

    @PostMapping("/password/forgot")
    public OtpSentResponse forgotPassword(@Valid @RequestBody OtpSendRequest req) {
        return otpService.sendPasswordReset(req.email());
    }

    @PostMapping("/password/reset")
    public TokenResponse resetPassword(@Valid @RequestBody PasswordResetRequest req) {
        return otpService.resetPassword(req.email(), req.code(), req.newPassword());
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public TokenResponse register(@Valid @RequestBody RegisterRequest req) {
        return authService.register(req);
    }

    @PostMapping("/login")
    public TokenResponse login(@Valid @RequestBody LoginRequest req) {
        return authService.login(req);
    }

    @GetMapping("/me")
    public UserView me(@AuthenticationPrincipal AuthUser principal) {
        return authService.me(principal);
    }
}
