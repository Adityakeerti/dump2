package com.citysense.platform.action;

/**
 * PENDING -> APPROVED | REJECTED (admin decision). LOW-risk actions skip the queue as AUTO_EXECUTED.
 * Every non-PENDING state is terminal.
 */
public enum ApprovalStatus {
    PENDING,
    APPROVED,
    REJECTED,
    AUTO_EXECUTED
}
