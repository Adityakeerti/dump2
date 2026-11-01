package com.citysense.agent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.multipart.MultipartFile;

/**
 * Seam between core and the Python agent_service (main voice agent + planner, port 8000).
 *
 * <p>Free-text chat is forwarded to {@code POST /api/agent/chat} with the caller's own bearer token
 * (core and agent_service share {@code JWT_SECRET}). When the agent is not configured, unreachable,
 * or the caller is anonymous, a local keyword responder answers so chat never hard-fails.
 */
@Component
public class AgentResponder {

    private static final Logger log = LoggerFactory.getLogger(AgentResponder.class);
    /** Lets agent_service's live dashboard attribute traffic to the phone app (which only talks to core). */
    static final String SOURCE_HEADER = "X-CitySense-Source";
    static final String SOURCE = "core-gateway";

    private final RestClient client;
    private final ObjectMapper json;
    private final boolean enabled;

    public AgentResponder(
            @Value("${citysense.agent.service-url:}") String agentUrl,
            @Value("${citysense.agent.timeout-seconds:30}") int timeoutSeconds,
            ObjectMapper json) {
        this.json = json;
        this.enabled = agentUrl != null && !agentUrl.isBlank();
        // HTTP/1.1 explicitly: the JDK client otherwise attempts an h2c upgrade on plain http://,
        // which uvicorn rejects with "400 Invalid HTTP request received".
        HttpClient http = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofSeconds(timeoutSeconds));
        this.client = RestClient.builder()
                .baseUrl(enabled ? agentUrl.replaceAll("/+$", "") : "http://agent-service.invalid")
                .requestFactory(factory)
                .build();
        log.info(enabled ? "AgentResponder proxying to {}" : "AgentResponder: no agent URL{}, using keyword fallback",
                enabled ? agentUrl : "");
    }

    public boolean isEnabled() {
        return enabled;
    }

    public AgentDtos.ChatResponse respond(AgentDtos.ChatRequest req) {
        String auth = currentAuthorization();
        if (enabled && auth != null) {
            try {
                return proxyChat(req, auth);
            } catch (RestClientException e) {
                log.warn("agent_service chat failed ({}); answering with keyword fallback", e.getMessage());
            }
        }
        return keywordFallback(req);
    }

    /**
     * Free-text chat with a map avatar: the avatar answers as a local area agent (area persona + web
     * search), and agent_service escalates emergencies and complaints to the main agent itself.
     */
    public AgentDtos.ChatResponse respondLocal(AgentDtos.LocalAvatar avatar, AgentDtos.ChatRequest req) {
        String auth = currentAuthorization();
        if (enabled && auth != null) {
            try {
                String lang = language(req.language());
                Map<String, Object> body = new LinkedHashMap<>();
                if (isUuid(req.sessionId())) {
                    body.put("sessionId", req.sessionId());
                }
                body.put("message", req.message());
                if (lang != null) {
                    body.put("language", lang);
                }
                body.put("avatar", avatar);
                return toChatResponse(post("/api/agent/local-chat", body, auth), req, lang);
            } catch (RestClientException e) {
                log.warn("agent_service local-chat failed ({}); answering with keyword fallback", e.getMessage());
            }
        }
        return keywordFallback(req);
    }

    // ── Pass-through for voice, TTS, action confirmation and audio preferences ─────────────────

    public ResponseEntity<byte[]> forwardJson(HttpMethod method, String path, Object body) {
        if (!enabled) {
            return unavailable();
        }
        try {
            RestClient.RequestBodySpec spec = client.method(method).uri(path).headers(this::copyAuth);
            if (body != null) {
                spec.contentType(MediaType.APPLICATION_JSON).body(body);
            }
            ResponseEntity<byte[]> upstream = spec.retrieve().toEntity(byte[].class);
            // Copy only the content type; hop-by-hop headers (transfer-encoding, etc.) must not leak.
            MediaType type = upstream.getHeaders().getContentType();
            return ResponseEntity.status(upstream.getStatusCode())
                    .contentType(type != null ? type : MediaType.APPLICATION_JSON)
                    .body(upstream.getBody());
        } catch (RestClientResponseException e) {
            return ResponseEntity.status(e.getStatusCode()).contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsByteArray());
        } catch (RestClientException e) {
            log.warn("agent_service {} {} failed: {}", method, path, e.getMessage());
            return unavailable();
        }
    }

    public ResponseEntity<byte[]> forwardAudio(MultipartFile file, String language) {
        return forwardMultipart("/api/agent/voice", file, "recording.m4a", language);
    }

    /** Uploads one file (voice clip, complaint photo) to agent_service as multipart field {@code file}. */
    public ResponseEntity<byte[]> forwardMultipart(String path, MultipartFile file, String defaultName, String language) {
        if (!enabled) {
            return unavailable();
        }
        try {
            MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
            String name = file.getOriginalFilename() != null ? file.getOriginalFilename() : defaultName;
            form.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return name;
                }
            });
            if (language != null && !language.isBlank()) {
                form.add("language", language);
            }
            byte[] out = client.post().uri(path).headers(this::copyAuth)
                    .contentType(MediaType.MULTIPART_FORM_DATA).body(form)
                    .retrieve().body(byte[].class);
            return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(out);
        } catch (RestClientResponseException e) {
            return ResponseEntity.status(e.getStatusCode()).contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsByteArray());
        } catch (Exception e) {
            log.warn("agent_service upload to {} failed: {}", path, e.getMessage());
            return unavailable();
        }
    }

    // ── internals ────────────────────────────────────────────────────────────────────────────

    private static String language(String requested) {
        return "hi".equalsIgnoreCase(requested) ? "hi" : ("en".equalsIgnoreCase(requested) ? "en" : null);
    }

    private JsonNode post(String path, Object body, String auth) {
        JsonNode res = client.post().uri(path)
                .header(HttpHeaders.AUTHORIZATION, auth)
                .header(SOURCE_HEADER, SOURCE)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class);
        if (res == null) {
            throw new RestClientException("empty agent response");
        }
        return res;
    }

    private AgentDtos.ChatResponse proxyChat(AgentDtos.ChatRequest req, String auth) {
        String lang = language(req.language());
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("cityId", "dehradun");
        if (req.latitude() != null && req.longitude() != null) {
            context.put("latitude", req.latitude());
            context.put("longitude", req.longitude());
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("requestId", UUID.randomUUID().toString());
        if (isUuid(req.sessionId())) {
            body.put("sessionId", req.sessionId());
        }
        body.put("agentId", "general"); // the agent's planner routes to specialists itself
        body.put("message", req.message());
        if (lang != null) {
            body.put("language", lang);
        }
        body.put("context", context);

        return toChatResponse(post("/api/agent/chat", body, auth), req, lang);
    }

    private AgentDtos.ChatResponse toChatResponse(JsonNode res, AgentDtos.ChatRequest req, String lang) {
        List<String> sources = new ArrayList<>();
        res.path("sources").forEach(s -> sources.add(s.path("title").asText()));
        String status = res.path("status").asText("ANSWERED");
        return new AgentDtos.ChatResponse(
                res.path("sessionId").asText(req.sessionId()),
                res.path("answer").asText(""),
                req.persona() != null ? req.persona() : res.path("agent").path("id").asText("general"),
                lang != null ? lang : "en",
                sources,
                "ABSTAINED".equals(status),
                Instant.now(),
                status,
                listOfMaps(res.path("plan")),
                map(res.path("pendingAction")),
                map(res.path("actionData")),
                "agent_service:" + res.path("served").asText("live"));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(JsonNode node) {
        return node == null || node.isMissingNode() || node.isNull() ? null : json.convertValue(node, Map.class);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> listOfMaps(JsonNode node) {
        return node == null || !node.isArray() ? null : json.convertValue(node, List.class);
    }

    private void copyAuth(HttpHeaders headers) {
        headers.set(SOURCE_HEADER, SOURCE);
        String auth = currentAuthorization();
        if (auth != null) {
            headers.set(HttpHeaders.AUTHORIZATION, auth);
        }
    }

    private static String currentAuthorization() {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs) {
            HttpServletRequest request = attrs.getRequest();
            String header = request.getHeader(HttpHeaders.AUTHORIZATION);
            return header != null && header.regionMatches(true, 0, "Bearer ", 0, 7) ? header : null;
        }
        return null;
    }

    private static boolean isUuid(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            UUID.fromString(value);
            return true;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    private static ResponseEntity<byte[]> unavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"Agent service unavailable\"}".getBytes());
    }

    /** Offline keyword responder: used only when agent_service cannot answer. */
    AgentDtos.ChatResponse keywordFallback(AgentDtos.ChatRequest req) {
        String sessId = req.sessionId() != null && !req.sessionId().isBlank() ? req.sessionId() : UUID.randomUUID().toString();
        String persona = req.persona() != null ? req.persona().toUpperCase(Locale.ROOT) : "CIVIC";
        String lang = req.language() != null ? req.language() : "en";
        String msg = req.message().toLowerCase(Locale.ROOT);
        boolean hi = "hi".equalsIgnoreCase(lang);

        String reply;
        List<String> sources;
        if (msg.contains("pothole") || msg.contains("road") || msg.contains("gaddha")) {
            reply = hi
                    ? "सड़क पर गड्ढे की शिकायत नगर निगम (PWD) को दर्ज की जा सकती है। आप 'Report' टैब से फोटो और जीपीएस लोकेशन भेज सकते हैं।"
                    : "Potholes and road damage can be reported via the 'Report' tab with GPS coordinates and a photo.";
            sources = List.of("CitySense offline guidance");
        } else if (msg.contains("water") || msg.contains("leak") || msg.contains("paani")) {
            reply = hi
                    ? "पानी की आपूर्ति या पाइपलाइन लीकेज संबंधी समस्या उत्तराखंड जल संस्थान को भेजी जाती है।"
                    : "Water supply disruption or pipeline leaks are routed to Uttarakhand Jal Sansthan.";
            sources = List.of("CitySense offline guidance");
        } else if (msg.contains("hospital") || msg.contains("ambulance") || msg.contains("accident") || msg.contains("aspatal")) {
            reply = hi
                    ? "आपात स्थिति में तुरंत 112 (आपातकाल) या 108 (एम्बुलेंस) पर कॉल करें।"
                    : "In an emergency call 112 (integrated emergency) or 108 (ambulance) immediately.";
            sources = List.of("CitySense offline guidance");
        } else {
            reply = hi
                    ? "मैं आपकी स्मार्ट सिटी सेवाओं में सहायता कर सकता हूँ: शिकायत दर्ज करना, यातायात, मौसम या आपातकालीन सेवाएँ।"
                    : "I am your CitySense Assistant. I can help you report civic grievances, check weather/flood routes, or reach emergency services.";
            sources = List.of();
        }
        return new AgentDtos.ChatResponse(sessId, reply, persona, lang, sources, false, Instant.now(),
                "ANSWERED", null, null, null, "core:keyword-fallback");
    }
}
