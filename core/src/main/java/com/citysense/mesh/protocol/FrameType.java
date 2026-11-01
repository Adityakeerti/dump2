package com.citysense.mesh.protocol;

/**
 * Constants for mesh frame discriminators.
 * Follows Knit's layered protocol specifications:
 * - CHAT: broadcast room or 1:1 direct message
 * - SOS: critical emergency distress beacon with victim location & triage needs
 * - FIELD_REPORT: offline civic hazard / observation report (flood, crash, blockage)
 * - RECEIPT: delivery / hop acknowledgment
 * - PROFILE: node presence advertisement and role
 * - DIGEST_SYNC: content digest exchange for store-and-forward delta pull
 */
public final class FrameType {
    public static final String CHAT = "chat";
    public static final String SOS = "sos";
    public static final String FIELD_REPORT = "field_report";
    public static final String RECEIPT = "receipt";
    public static final String PROFILE = "profile";
    public static final String DIGEST_SYNC = "digest_sync";

    private FrameType() {}

    public static boolean isCustodial(String type) {
        return CHAT.equals(type) || SOS.equals(type) || FIELD_REPORT.equals(type) || PROFILE.equals(type);
    }
}
