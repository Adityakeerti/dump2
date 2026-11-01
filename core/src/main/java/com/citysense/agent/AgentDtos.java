package com.citysense.agent;

import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public class AgentDtos {

    public record ChatRequest(
            @NotBlank String message,
            String persona,
            String language,
            String sessionId,
            Double latitude,
            Double longitude
    ) {
        public ChatRequest(String message, String persona, String language, String sessionId) {
            this(message, persona, language, sessionId, null, null);
        }
    }

    /**
     * Reply from the agent. {@code status}, {@code plan}, {@code pendingAction} and {@code actionData}
     * are populated when the Python agent_service answered; the local keyword fallback leaves them null.
     */
    public record ChatResponse(
            String sessionId,
            String reply,
            String persona,
            String language,
            List<String> sources,
            boolean abstained,
            Instant timestamp,
            String status,
            List<Map<String, Object>> plan,
            Map<String, Object> pendingAction,
            Map<String, Object> actionData,
            String servedBy
    ) {}

    /** A map avatar answering as a local area agent (persona + area + web search in agent_service). */
    public record LocalAvatar(
            String handle,
            String name,
            String title,
            String persona,
            String category,
            String intro,
            double latitude,
            double longitude
    ) {}

    public record PersonaView(
            String id,
            String name,
            String role,
            String description,
            List<String> supportedLanguages
    ) {}

    public record KnowledgeDocRequest(
            @NotBlank String title,
            @NotBlank String category,
            String department,
            String content,
            String sourceUrl
    ) {}

    public record KnowledgeDocResponse(
            String id,
            String title,
            String category,
            String department,
            boolean isVerified,
            Instant createdAt
    ) {}
}
