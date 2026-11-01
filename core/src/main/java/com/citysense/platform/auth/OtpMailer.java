package com.citysense.platform.auth;

import com.citysense.common.error.ApiException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

/** Delivers OTP codes by SMTP when spring.mail.host is configured, else (dev only) to the log. */
@Component
public class OtpMailer {

    private static final Logger log = LoggerFactory.getLogger(OtpMailer.class);

    private final ObjectProvider<JavaMailSender> mailSender;
    private final OtpProperties props;
    private final boolean smtpConfigured;

    // An empty SPRING_MAIL_HOST (e.g. passed through by docker compose) still creates a mail sender
    // bean, so the host itself decides whether SMTP is configured.
    public OtpMailer(ObjectProvider<JavaMailSender> mailSender, OtpProperties props,
                     @Value("${spring.mail.host:}") String mailHost) {
        this.mailSender = mailSender;
        this.props = props;
        this.smtpConfigured = mailHost != null && !mailHost.isBlank();
    }

    public void send(String email, String code, OtpPurpose purpose) {
        JavaMailSender sender = smtpConfigured ? mailSender.getIfAvailable() : null;
        if (sender == null) {
            if (!props.logFallback()) {
                throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "Email delivery is not configured");
            }
            log.warn("SMTP not configured (set SPRING_MAIL_HOST). DEV {} OTP for {}: {}", purpose, email, code);
            return;
        }
        SimpleMailMessage msg = new SimpleMailMessage();
        msg.setFrom(props.mailFrom());
        msg.setTo(email);
        msg.setSubject(props.mailSubject());
        String what = purpose == OtpPurpose.RESET_PASSWORD ? "password reset" : "verification";
        msg.setText("Your CitySense " + what + " code is " + code + ". It expires in "
                + (props.ttlSeconds() / 60) + " minutes. If you did not request it, ignore this email.");
        try {
            sender.send(msg);
        } catch (MailException e) {
            log.error("Failed to send OTP email to {}: {}", email, e.getMessage());
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "Could not send the verification email; try again");
        }
    }
}
