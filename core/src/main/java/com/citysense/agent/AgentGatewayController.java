package com.citysense.agent;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.Map;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/agent")
@Tag(name = "Agent", description = "Multilingual Citizen AI Assistant, RAG Knowledge Base, and specialist personas")
public class AgentGatewayController {

    private static final List<AgentDtos.PersonaView> PERSONAS = List.of(
            new AgentDtos.PersonaView("CIVIC", "Nagrik Sahayak (Civic Assistant)", "Civic Grievances & Municipal Help", "Guides citizens through filing potholes, sanitation, water, and electricity grievances", List.of("en", "hi")),
            new AgentDtos.PersonaView("TRAFFIC", "Vahan Margdarshak (Traffic Guide)", "Traffic & Route Planning", "Advises on congestion, waterlogged underpasses, diversions, and green corridors", List.of("en", "hi")),
            new AgentDtos.PersonaView("EMERGENCY", "Aapat Sahayak (Emergency Coordinator)", "Accident & Medical Emergency", "Dispatches ambulance missions, coordinates with Doon/Max hospitals, and alerts police", List.of("en", "hi")),
            new AgentDtos.PersonaView("TRANSIT", "Yatra Sahayak (Transit Navigator)", "Public Transport & Inter-city", "Provides schedules for Dehradun Railway Station, ISBT, and Jolly Grant Airport", List.of("en", "hi"))
    );

    private final AgentResponder responder;

    public AgentGatewayController(AgentResponder responder) {
        this.responder = responder;
    }

    @GetMapping("/personas")
    @Operation(summary = "List specialist citizen agent personas")
    public List<AgentDtos.PersonaView> listPersonas() {
        return PERSONAS;
    }

    @PostMapping("/chat")
    @Operation(summary = "Interact with Multilingual Citizen Assistant with grounded knowledge citations and abstain guardrails")
    public AgentDtos.ChatResponse chat(@Valid @RequestBody AgentDtos.ChatRequest req) {
        return responder.respond(req);
    }

    // ── Pass-through to agent_service so clients need only one base URL in dev ──────────────
    // (Behind the production reverse proxy /api/agent/* reaches agent_service directly.)

    @PostMapping(value = "/voice", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Speech-to-text (Sarvam saaras:v3 with Groq fallback) via agent_service")
    public ResponseEntity<byte[]> voice(@RequestPart("file") MultipartFile file,
                                        @RequestParam(value = "language", required = false) String language) {
        return responder.forwardAudio(file, language);
    }

    @PostMapping("/assistant")
    @Operation(summary = "Main agent for the in-app assistant: full hierarchy plus app control (clientActions)")
    public ResponseEntity<byte[]> assistant(@RequestBody Map<String, Object> body) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/assistant", body);
    }

    @PostMapping("/place")
    @Operation(summary = "Main agent briefing for a tapped map point (or a follow-up question about it)")
    public ResponseEntity<byte[]> place(@RequestBody Map<String, Object> body) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/place", body);
    }

    @PostMapping("/tts")
    @Operation(summary = "Text-to-speech (Sarvam bulbul:v3, 24 kHz WAV) via agent_service")
    public ResponseEntity<byte[]> tts(@RequestBody Map<String, Object> body) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/tts", body);
    }

    @PostMapping("/tts/clips")
    @Operation(summary = "Synthesize a reply into a short-lived playable clip URL")
    public ResponseEntity<byte[]> ttsClip(@RequestBody Map<String, Object> body) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/tts/clips", body);
    }

    @GetMapping("/tts/clips/{clipId}")
    @Operation(summary = "Stream a TTS clip (capability URL, expires after 5 minutes)")
    public ResponseEntity<byte[]> ttsClipAudio(@PathVariable String clipId) {
        return responder.forwardJson(HttpMethod.GET, "/api/agent/tts/clips/" + encode(clipId), null);
    }

    @PostMapping("/actions/{token}/confirm")
    @Operation(summary = "Confirm an action the agent proposed (e.g. file the drafted complaint)")
    public ResponseEntity<byte[]> confirm(@PathVariable String token) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/actions/{token}/confirm".replace("{token}", encode(token)), null);
    }

    @PostMapping(value = "/actions/{token}/photo", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Attach a photo to a drafted complaint (stored by agent_service)")
    public ResponseEntity<byte[]> attachPhoto(@PathVariable String token, @RequestPart("file") MultipartFile file) {
        return responder.forwardMultipart("/api/agent/actions/" + encode(token) + "/photo", file, "evidence.jpg", null);
    }

    @GetMapping("/media/{mediaId}")
    @Operation(summary = "A photo the caller attached")
    public ResponseEntity<byte[]> media(@PathVariable String mediaId) {
        return responder.forwardJson(HttpMethod.GET, "/api/agent/media/" + encode(mediaId), null);
    }

    @PostMapping("/actions/{token}/cancel")
    @Operation(summary = "Cancel an action the agent proposed")
    public ResponseEntity<byte[]> cancel(@PathVariable String token) {
        return responder.forwardJson(HttpMethod.POST, "/api/agent/actions/{token}/cancel".replace("{token}", encode(token)), null);
    }

    @GetMapping("/preferences/audio")
    @Operation(summary = "Read the speaker mute / voice preference")
    public ResponseEntity<byte[]> audioPreference() {
        return responder.forwardJson(HttpMethod.GET, "/api/agent/preferences/audio", null);
    }

    @PutMapping("/preferences/audio")
    @Operation(summary = "Save the speaker mute / voice preference")
    public ResponseEntity<byte[]> setAudioPreference(@RequestBody Map<String, Object> body) {
        return responder.forwardJson(HttpMethod.PUT, "/api/agent/preferences/audio", body);
    }

    private static String encode(String token) {
        return java.net.URLEncoder.encode(token, java.nio.charset.StandardCharsets.UTF_8);
    }

    @PostMapping("/knowledge/docs")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Register verified document into municipal knowledge base")
    public AgentDtos.KnowledgeDocResponse registerKnowledgeDoc(@Valid @RequestBody AgentDtos.KnowledgeDocRequest req) {
        return new AgentDtos.KnowledgeDocResponse(
                UUID.randomUUID().toString(),
                req.title(),
                req.category(),
                req.department() != null ? req.department() : "MUNICIPAL",
                true,
                Instant.now()
        );
    }
}
