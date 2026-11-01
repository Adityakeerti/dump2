package com.citysense.civic;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Per-user complaint filing limit: at most {@code maxPerWindow} complaints in any sliding {@code window}
 * (default 10 per hour). Counted from the complaints table, so it survives restarts and holds across instances.
 */
@ConfigurationProperties(prefix = "citysense.civic.filing-limit")
public record ComplaintFilingLimit(int maxPerWindow, Duration window) {

    public ComplaintFilingLimit {
        if (maxPerWindow < 1) {
            throw new IllegalArgumentException("citysense.civic.filing-limit.max-per-window must be at least 1");
        }
        if (window == null || window.isNegative() || window.isZero()) {
            throw new IllegalArgumentException("citysense.civic.filing-limit.window must be a positive duration");
        }
    }
}
