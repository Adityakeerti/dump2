package com.citysense.platform.action;

public enum RiskLevel {
    LOW,
    MEDIUM,
    HIGH;

    public RiskLevel atLeast(RiskLevel floor) {
        return ordinal() >= floor.ordinal() ? this : floor;
    }
}
