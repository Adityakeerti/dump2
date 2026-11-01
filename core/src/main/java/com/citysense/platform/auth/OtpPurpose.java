package com.citysense.platform.auth;

/** A code issued for one purpose can never be redeemed for another. */
public enum OtpPurpose {
    VERIFY_EMAIL,
    RESET_PASSWORD
}
