package com.citysense.platform.action;

/** Each type carries a minimum risk; a proposer may raise it but never lower it. */
public enum ActionType {
    NOTIFY_CITIZENS(RiskLevel.LOW),
    SIGNAL_OVERRIDE(RiskLevel.HIGH),
    ROAD_CLOSURE(RiskLevel.HIGH),
    DISPATCH(RiskLevel.HIGH),
    EVACUATION(RiskLevel.HIGH),
    GREEN_CORRIDOR(RiskLevel.HIGH);

    private final RiskLevel minimumRisk;

    ActionType(RiskLevel minimumRisk) {
        this.minimumRisk = minimumRisk;
    }

    public RiskLevel minimumRisk() {
        return minimumRisk;
    }
}
