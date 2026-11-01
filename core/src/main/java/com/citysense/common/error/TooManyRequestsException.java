package com.citysense.common.error;

import java.time.Duration;
import org.springframework.http.HttpStatus;

/** 429 with the time until the caller may try again (sent as the {@code Retry-After} header, in seconds). */
public class TooManyRequestsException extends ApiException {

    private final Duration retryAfter;

    public TooManyRequestsException(String message, Duration retryAfter) {
        super(HttpStatus.TOO_MANY_REQUESTS, message);
        this.retryAfter = retryAfter;
    }

    public Duration retryAfter() {
        return retryAfter;
    }
}
