package com.citysense.avatar;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class AvatarDtos {

    private AvatarDtos() {}

    public record Socials(String instagram, String threads, String x) {}

    /** Image URLs are relative to the API base URL. distanceMeters is null when no origin was given. */
    public record AvatarView(UUID id, String handle, String name, String title, String category, String persona,
                             String intro, String pricing, String websiteUrl, Socials socials,
                             String pinImageUrl, String heroImageUrl, BigDecimal rating, int reviewCount,
                             long likeCount, double latitude, double longitude, Double distanceMeters,
                             boolean saved, boolean liked) {}

    public enum ChatIntent { INTRO, PRICING, WEBSITE }

    public record AvatarChatRequest(
            @Size(max = 2000) String message,
            ChatIntent intent,
            @Pattern(regexp = "^[a-z]{2}$") String language,
            @Size(max = 64) String sessionId,
            Double latitude,
            Double longitude) {}

    /** Agent-backed replies also carry the execution plan, a confirmable action and structured cards. */
    public record AvatarChatResponse(String sessionId, String reply, ChatIntent intent, String link,
                                     List<String> sources, Instant timestamp, String status,
                                     List<Map<String, Object>> plan, Map<String, Object> pendingAction,
                                     Map<String, Object> actionData) {}

    public record ToggleResponse(UUID avatarId, boolean active, long count) {}

}
