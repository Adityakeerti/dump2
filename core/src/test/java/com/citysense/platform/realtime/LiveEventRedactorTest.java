package com.citysense.platform.realtime;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class LiveEventRedactorTest {

    private final LiveEventRedactor redactor = new LiveEventRedactor(new ObjectMapper().findAndRegisterModules());

    @SuppressWarnings("unchecked")
    private Map<String, Object> redacted(String type, Map<String, Object> data) {
        CityEventMessage out = redactor.redact(new CityEventMessage(type, "e1", data, Instant.now()));
        assertThat(out.type()).isEqualTo(type);
        assertThat(out.entityId()).isEqualTo("e1");
        return (Map<String, Object>) out.data();
    }

    private static Map<String, Object> map(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    @Test
    void fullComplaintRecordsAreCutToThePublicSummary() {
        // Even if a service publishes the full ComplaintResponse again, nothing personal gets out.
        Map<String, Object> out = redacted("COMPLAINT_FILED", map("id", "c1", "trackingId", "CS-ABC", "citizenName", "Asha Rawat",
                "title", "Leak at house 12", "description", "my phone 98765 43210", "latitude", 30.32431, "longitude", 78.04182,
                "photoUrl", "http://x", "assignedWorker", "crew@x", "resolutionNotes", "n", "category", "CIVIC",
                "department", "JAL_SANSTHAN", "status", "FILED", "priority", "HIGH"));
        assertThat(out.keySet()).containsExactlyInAnyOrder("id", "title", "category", "department", "status", "priority");
    }

    @Test
    void meshEventsRevealOnlyThatSomethingArrived() {
        Map<String, Object> sos = redacted("MESH_SOS_RECEIVED", map("id", "sos-1", "senderId", "node-7",
                "sos", map("victimName", "Ravi", "medicalNeeds", "insulin", "latitude", 30.1, "longitude", 78.1)));
        assertThat(sos).containsOnlyKeys("id");
        Map<String, Object> dm = redacted("MESH_CHAT_RECEIVED", map("id", "m1", "recipientId", "node-9",
                "chat", map("body", "private message", "senderName", "Meera")));
        assertThat(dm).containsOnlyKeys("id");
        assertThat(redacted("MESH_FIELD_REPORT_RECEIVED", map("id", "r1", "report", map("description", "x")))).containsOnlyKeys("id");
    }

    @Test
    void observationPayloadsSourcesAndCoordinatesAreDropped() {
        Map<String, Object> out = redacted("OBSERVATION_CREATED", map("id", "o1", "type", "CRASH", "status", "VERIFIED",
                "incidentId", "i1", "observedAt", "2026-10-31T10:00:00Z", "source", "mesh:node-7",
                "latitude", 30.32431, "longitude", 78.04182, "payload", map("victim_name", "Ravi")));
        assertThat(out.keySet()).containsExactlyInAnyOrder("id", "type", "status", "incidentId", "observedAt");
    }

    @Test
    void actionPayloadsAndReasonsAreDropped() {
        Map<String, Object> out = redacted("ACTION_PENDING", map("id", "a1", "incidentId", "i1", "actionType", "NOTIFY",
                "riskLevel", "HIGH", "approvalStatus", "PENDING", "createdAt", "t", "summary", "Call +91 98765",
                "payload", map("phone", "+919876543210"), "decisionReason", "r", "decidedBy", "u1", "agent", "coordinator"));
        assertThat(out.keySet()).containsExactlyInAnyOrder("id", "incidentId", "actionType", "riskLevel", "approvalStatus", "createdAt");
    }

    @Test
    void incidentsKeepTheirTitleButOnlyACoarseLocation() {
        Map<String, Object> out = redacted("INCIDENT_CREATED", map("id", "i1", "type", "FLOOD", "title", "Flooding",
                "summary", "Reported by Asha at house 12", "severity", 3, "status", "OPEN", "observationCount", 2,
                "latitude", 30.32431, "longitude", 78.04182, "urgencyScore", 0.7, "createdAt", "t", "updatedAt", "t"));
        assertThat(out).doesNotContainKeys("summary", "urgencyScore").containsEntry("title", "Flooding")
                .containsEntry("latitude", 30.32).containsEntry("longitude", 78.04);
    }

    @Test
    void unknownEventTypesAreDeniedByDefault() {
        assertThat(redacted("SOMETHING_NEW", map("id", "x", "email", "a@b.c"))).isEmpty();
        assertThat(redacted("COMPLAINT_FILED", null)).isEmpty();
    }

    @Test
    void publicBulletinsPassThrough() {
        assertThat(redacted("CITY_EVENT_CREATED", map("id", "b1", "title", "Road closed", "severity", "WARNING",
                "latitude", 30.3, "longitude", 78.0))).containsKeys("title", "severity", "latitude");
    }
}
