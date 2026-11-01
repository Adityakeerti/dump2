package com.citysense.platform.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.citysense.common.config.CitySenseProperties;
import com.citysense.common.error.ApiException;
import com.citysense.platform.audit.AuditService;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;

class OtpServiceTest {

    private final OtpProperties props = new OtpProperties(4, 300, 3, 30, "from@x", "subj", true);
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(4);
    private UserRepository users;
    private EmailOtpRepository otps;
    private OtpMailer mailer;
    private OtpService service;
    private User user;

    @BeforeEach
    void setUp() {
        users = mock(UserRepository.class);
        otps = mock(EmailOtpRepository.class);
        mailer = mock(OtpMailer.class);
        JwtService jwt = new JwtService(new CitySenseProperties(1,
                new CitySenseProperties.Security("test-secret-test-secret-test-secret-123", 60, "k", "*"), null, null));
        service = new OtpService(users, otps, encoder, mailer, props, jwt, mock(AuditService.class));
        user = new User("a@b.dev", "hash", "A", Role.CITIZEN, "en");
        ReflectionTestUtils.setField(user, "id", UUID.randomUUID());
        when(users.findByEmailIgnoreCase("a@b.dev")).thenReturn(Optional.of(user));
    }

    @Test
    void issueStoresHashNotCodeAndMailsCode() {
        service.issue(user, OtpPurpose.VERIFY_EMAIL);
        ArgumentCaptor<String> code = ArgumentCaptor.forClass(String.class);
        verify(mailer).send(eq("a@b.dev"), code.capture(), eq(OtpPurpose.VERIFY_EMAIL));
        ArgumentCaptor<EmailOtp> saved = ArgumentCaptor.forClass(EmailOtp.class);
        verify(otps).save(saved.capture());
        assertThat(code.getValue()).matches("\\d{4}");
        assertThat(saved.getValue().getCodeHash()).isNotEqualTo(code.getValue());
        assertThat(encoder.matches(code.getValue(), saved.getValue().getCodeHash())).isTrue();
    }

    @Test
    void sendForUnknownEmailLooksIdenticalButMailsNothing() {
        when(users.findByEmailIgnoreCase("nobody@b.dev")).thenReturn(Optional.empty());
        var res = service.send("nobody@b.dev");
        assertThat(res.codeLength()).isEqualTo(4);
        assertThat(res.resendAfterSeconds()).isEqualTo(30);
        verify(mailer, never()).send(anyString(), anyString(), any());
    }

    @Test
    void sendWithinCooldownDoesNotResend() {
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.VERIFY_EMAIL))
                .thenReturn(Optional.of(new EmailOtp(user.getId(), OtpPurpose.VERIFY_EMAIL, "h", Instant.now().plusSeconds(300))));
        var res = service.send("a@b.dev");
        assertThat(res.resendAfterSeconds()).isBetween(1L, 30L);
        verify(mailer, never()).send(anyString(), anyString(), any());
    }

    @Test
    void correctCodeVerifiesUserAndIssuesVerifiedToken() {
        EmailOtp otp = new EmailOtp(user.getId(), OtpPurpose.VERIFY_EMAIL, encoder.encode("1234"), Instant.now().plusSeconds(300));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.VERIFY_EMAIL)).thenReturn(Optional.of(otp));
        var token = service.verify("a@b.dev", "1234");
        assertThat(user.isEmailVerified()).isTrue();
        assertThat(otp.isConsumed()).isTrue();
        assertThat(token.user().emailVerified()).isTrue();
    }

    @Test
    void wrongCodesCountDownThenLock() {
        EmailOtp otp = new EmailOtp(user.getId(), OtpPurpose.VERIFY_EMAIL, encoder.encode("1234"), Instant.now().plusSeconds(300));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.VERIFY_EMAIL)).thenReturn(Optional.of(otp));
        for (int i = 0; i < 3; i++) {
            assertThatThrownBy(() -> service.verify("a@b.dev", "0000")).isInstanceOf(ApiException.class);
        }
        assertThatThrownBy(() -> service.verify("a@b.dev", "1234"))
                .isInstanceOfSatisfying(ApiException.class,
                        e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS));
        assertThat(user.isEmailVerified()).isFalse();
    }

    @Test
    void expiredCodeIsRejected() {
        EmailOtp otp = new EmailOtp(user.getId(), OtpPurpose.VERIFY_EMAIL, encoder.encode("1234"), Instant.now().minusSeconds(1));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.VERIFY_EMAIL)).thenReturn(Optional.of(otp));
        assertThatThrownBy(() -> service.verify("a@b.dev", "1234")).isInstanceOf(ApiException.class);
        assertThat(user.isEmailVerified()).isFalse();
    }

    @Test
    void reissueInvalidatesPreviousCodes() {
        EmailOtp old = new EmailOtp(user.getId(), OtpPurpose.VERIFY_EMAIL, "h", Instant.now().plusSeconds(300));
        when(otps.findByUserIdAndPurposeAndConsumedAtIsNull(user.getId(), OtpPurpose.VERIFY_EMAIL)).thenReturn(List.of(old));
        service.issue(user, OtpPurpose.VERIFY_EMAIL);
        assertThat(old.isConsumed()).isTrue();
        verify(otps).save(any(EmailOtp.class));
    }

    @Test
    void resetCodeCannotVerifyEmailAndViceVersa() {
        EmailOtp resetOtp = new EmailOtp(user.getId(), OtpPurpose.RESET_PASSWORD, encoder.encode("1234"),
                Instant.now().plusSeconds(300));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.RESET_PASSWORD))
                .thenReturn(Optional.of(resetOtp));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.VERIFY_EMAIL))
                .thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.verify("a@b.dev", "1234")).isInstanceOf(ApiException.class);
        assertThat(user.isEmailVerified()).isFalse();
    }

    @Test
    void resetPasswordChangesHashAndVerifies() {
        EmailOtp otp = new EmailOtp(user.getId(), OtpPurpose.RESET_PASSWORD, encoder.encode("4321"),
                Instant.now().plusSeconds(300));
        when(otps.findFirstByUserIdAndPurposeOrderByCreatedAtDesc(user.getId(), OtpPurpose.RESET_PASSWORD))
                .thenReturn(Optional.of(otp));
        var token = service.resetPassword("a@b.dev", "4321", "new-password-1");
        assertThat(encoder.matches("new-password-1", user.getPasswordHash())).isTrue();
        assertThat(token.user().emailVerified()).isTrue();
        assertThat(otp.isConsumed()).isTrue();
    }

    @Test
    void forgotForUnknownEmailLooksIdentical() {
        when(users.findByEmailIgnoreCase("ghost@b.dev")).thenReturn(Optional.empty());
        var res = service.sendPasswordReset("ghost@b.dev");
        assertThat(res.resendAfterSeconds()).isEqualTo(30);
        verify(mailer, never()).send(anyString(), anyString(), any());
    }
}
