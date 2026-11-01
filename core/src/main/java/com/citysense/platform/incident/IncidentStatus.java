package com.citysense.platform.incident;

public enum IncidentStatus {
    OPEN,
    ACKNOWLEDGED,
    RESOLVED;

    /** Incidents only move forward; a resolved incident is never reopened (a new one is created instead). */
    public boolean canMoveTo(IncidentStatus next) {
        return next.ordinal() > ordinal();
    }
}
