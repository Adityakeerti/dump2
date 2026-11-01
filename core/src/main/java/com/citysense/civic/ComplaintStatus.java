package com.citysense.civic;

import com.citysense.common.error.ApiException;
import java.util.Arrays;
import java.util.Locale;
import org.springframework.http.HttpStatus;

/** Complaint lifecycle states; mirrors the CHECK constraint on complaints.status (V3). */
public enum ComplaintStatus {
    FILED, ASSIGNED, IN_PROGRESS, RESOLVED, REJECTED, ESCALATED;

    /** Parses client input; unknown values are a 400 (previously they reached the DB and became a 500). */
    public static ComplaintStatus parse(String value) {
        if (value != null) {
            try {
                return valueOf(value.trim().toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException ignored) {
                // fall through
            }
        }
        throw new ApiException(HttpStatus.BAD_REQUEST,
                "status must be one of " + Arrays.toString(values()));
    }
}
