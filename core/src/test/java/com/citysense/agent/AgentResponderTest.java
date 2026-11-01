package com.citysense.agent;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class AgentResponderTest {

    private static final String AGENT_REPLY = """
            {"sessionId":"7d3c3a8e-1111-4c3e-9f00-000000000001","messageId":"7d3c3a8e-1111-4c3e-9f00-000000000002",
             "status":"ACTION_PENDING","answer":"Draft ready","agent":{"id":"general","name":"City Sense"},
             "sources":[{"title":"NND Rules"}],"served":"live",
             "plan":[{"id":1,"executor":"civic_complaint","action":"Draft","tools":["create_complaint"],"status":"completed"}],
             "pendingAction":{"token":"tok-1","summary":"Complaint","expiresAt":"2026-11-01T00:00:00Z"},
             "actionData":{"location":{"location":"Clock Tower"}}}
            """;

    private HttpServer server;
    private final AtomicReference<String> seenAuth = new AtomicReference<>();
    private final AtomicReference<String> seenBody = new AtomicReference<>();
    private final ObjectMapper json = new ObjectMapper();

    @BeforeEach
    void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/agent/chat", exchange -> {
            seenAuth.set(exchange.getRequestHeaders().getFirst("Authorization")
                    + "|" + exchange.getRequestHeaders().getFirst("X-CitySense-Source"));
            seenBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] out = AGENT_REPLY.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, out.length);
            exchange.getResponseBody().write(out);
            exchange.close();
        });
        server.createContext("/api/agent/local-chat", exchange -> {
            seenBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] out = AGENT_REPLY.replace("\"general\",\"name\":\"City Sense\"", "\"local:amit\",\"name\":\"Amit\"")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, out.length);
            exchange.getResponseBody().write(out);
            exchange.close();
        });
        server.start();
    }

    @AfterEach
    void stop() {
        server.stop(0);
        RequestContextHolder.resetRequestAttributes();
    }

    private void bearer(String token) {
        MockHttpServletRequest req = new MockHttpServletRequest();
        if (token != null) {
            req.addHeader("Authorization", "Bearer " + token);
        }
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(req));
    }

    private String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @Test
    void proxiesToAgentServiceWithCallersTokenAndMapsPlan() throws Exception {
        bearer("user-jwt");
        AgentResponder responder = new AgentResponder(url(), 5, json);

        AgentDtos.ChatResponse r = responder.respond(
                new AgentDtos.ChatRequest("pothole near clock tower", "CIVIC", "en", "not-a-uuid", 30.32, 78.04));

        assertThat(seenAuth.get()).isEqualTo("Bearer user-jwt|core-gateway");
        var body = json.readTree(seenBody.get());
        assertThat(body.path("agentId").asText()).isEqualTo("general");
        assertThat(body.has("sessionId")).as("non-UUID session ids are not forwarded").isFalse();
        assertThat(body.path("context").path("latitude").asDouble()).isEqualTo(30.32);
        assertThat(r.status()).isEqualTo("ACTION_PENDING");
        assertThat(r.sessionId()).isEqualTo("7d3c3a8e-1111-4c3e-9f00-000000000001");
        assertThat(r.plan()).hasSize(1);
        assertThat(r.pendingAction()).containsEntry("token", "tok-1");
        assertThat(r.sources()).containsExactly("NND Rules");
        assertThat(r.servedBy()).isEqualTo("agent_service:live");
    }

    @Test
    void avatarChatGoesToLocalAgentWithAreaContext() throws Exception {
        bearer("user-jwt");
        AgentResponder responder = new AgentResponder(url(), 5, json);
        AgentDtos.ChatResponse r = responder.respondLocal(
                new AgentDtos.LocalAvatar("amit", "Amit", "Paltan Bazaar shopping guide", "TRANSIT", "GUIDE",
                        "I help shoppers.", 30.3226, 78.0436),
                new AgentDtos.ChatRequest("best woollens?", "TRANSIT", "en", null));
        var body = json.readTree(seenBody.get());
        assert body.path("avatar").path("handle").asText().equals("amit");
        assert body.path("avatar").path("latitude").asDouble() == 30.3226;
        assert body.path("message").asText().equals("best woollens?");
        assert r.servedBy().startsWith("agent_service");
    }

    @Test
    void fallsBackWhenAnonymousOrUnconfiguredOrDown() {
        bearer(null);
        assertThat(new AgentResponder(url(), 5, json).respond(new AgentDtos.ChatRequest("hello", null, "en", null))
                .servedBy()).isEqualTo("core:keyword-fallback");
        assertThat(seenBody.get()).as("anonymous callers never reach the agent").isNull();

        bearer("user-jwt");
        assertThat(new AgentResponder("", 5, json).respond(new AgentDtos.ChatRequest("hello", null, "en", null))
                .servedBy()).isEqualTo("core:keyword-fallback");

        server.stop(0);
        AgentDtos.ChatResponse down = new AgentResponder(url(), 2, json)
                .respond(new AgentDtos.ChatRequest("ambulance needed", null, "en", null));
        assertThat(down.servedBy()).isEqualTo("core:keyword-fallback");
        assertThat(down.reply()).contains("112");
    }
}
