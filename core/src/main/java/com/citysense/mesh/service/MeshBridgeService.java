package com.citysense.mesh.service;

import com.citysense.mesh.protocol.ChatPayload;
import com.citysense.mesh.protocol.FieldReportPayload;
import com.citysense.mesh.protocol.FrameType;
import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.SosPayload;
import com.citysense.mesh.protocol.WireCodec;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationService;
import com.citysense.platform.observation.ObservationStatus;
import com.citysense.platform.observation.ObservationType;
import com.citysense.platform.realtime.CityEventMessage;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

/**
 * Bridges offline mesh packets into the core CitySense platform.
 * Ingests offline emergency distress signals (SOS) and field reports directly into
 * the CitySense CorrelationEngine and broadcasts real-time updates over WebSocket STOMP.
 */
@Service
public class MeshBridgeService {

    private static final Logger log = LoggerFactory.getLogger(MeshBridgeService.class);

    private final ObservationService observationService;
    private final ApplicationEventPublisher eventPublisher;

    public MeshBridgeService(ObservationService observationService, ApplicationEventPublisher eventPublisher) {
        this.observationService = observationService;
        this.eventPublisher = eventPublisher;
    }

    public void processInbound(RelayEnvelope relay) {
        if (relay == null) return;

        try {
            switch (relay.getType()) {
                case FrameType.SOS -> handleSos(relay);
                case FrameType.FIELD_REPORT -> handleFieldReport(relay);
                case FrameType.CHAT -> handleChat(relay);
                default -> log.debug("Handled unbridged frame type: {}", relay.getType());
            }
        } catch (Exception e) {
            log.error("Failed to bridge mesh frame {}: {}", relay.getId(), e.getMessage(), e);
        }
    }

    private void handleSos(RelayEnvelope relay) {
        SosPayload sos = WireCodec.decodePayload(relay.getPayload(), SosPayload.class);
        log.warn("🚨 EMERGENCY MESH SOS RECEIVED from {}: Type={}, Victim={}, Lat={}, Lon={}",
                relay.getSenderId(), sos.emergencyType(), sos.victimName(), sos.latitude(), sos.longitude());

        ObservationType obsType = mapEmergencyToObservationType(sos.emergencyType());
        Map<String, Object> payloadMap = new HashMap<>();
        payloadMap.put("source_mesh_id", relay.getId());
        payloadMap.put("sender_id", relay.getSenderId());
        payloadMap.put("victim_name", sos.victimName());
        payloadMap.put("urgency_score", sos.urgencyScore());
        payloadMap.put("injuries_count", sos.injuriesCount());
        payloadMap.put("medical_needs", sos.medicalNeeds());
        payloadMap.put("details", sos.details());
        payloadMap.put("transport", "OFFLINE_MESH");

        ObservationRequest req = new ObservationRequest(
                obsType,
                sos.latitude(),
                sos.longitude(),
                Instant.ofEpochMilli(relay.getSentAt()),
                "mesh:" + relay.getSenderId(),
                1.0,
                ObservationStatus.VERIFIED,
                payloadMap
        );

        observationService.ingest(req, "mesh-gateway");

        eventPublisher.publishEvent(CityEventMessage.of(
                "MESH_SOS_RECEIVED",
                relay.getId(),
                Map.of(
                        "id", relay.getId(),
                        "senderId", relay.getSenderId(),
                        "sos", sos,
                        "sentAt", relay.getSentAt()
                )
        ));
    }

    private void handleFieldReport(RelayEnvelope relay) {
        FieldReportPayload report = WireCodec.decodePayload(relay.getPayload(), FieldReportPayload.class);
        log.info("📢 Offline Mesh Field Report from {}: Type={}, Severity={}, Lat={}, Lon={}",
                relay.getSenderId(), report.reportType(), report.severity(), report.latitude(), report.longitude());

        ObservationType obsType = mapFieldReportToObservationType(report.reportType());
        Map<String, Object> payloadMap = new HashMap<>();
        payloadMap.put("source_mesh_id", relay.getId());
        payloadMap.put("sender_id", relay.getSenderId());
        payloadMap.put("reporter_role", report.reporterRole());
        payloadMap.put("severity", report.severity());
        payloadMap.put("description", report.description());
        payloadMap.put("transport", "OFFLINE_MESH");

        ObservationRequest req = new ObservationRequest(
                obsType,
                report.latitude(),
                report.longitude(),
                Instant.ofEpochMilli(relay.getSentAt()),
                "mesh:" + relay.getSenderId(),
                0.9,
                ObservationStatus.UNVERIFIED,
                payloadMap
        );

        observationService.ingest(req, "mesh-gateway");

        eventPublisher.publishEvent(CityEventMessage.of(
                "MESH_FIELD_REPORT_RECEIVED",
                relay.getId(),
                Map.of(
                        "id", relay.getId(),
                        "senderId", relay.getSenderId(),
                        "report", report,
                        "sentAt", relay.getSentAt()
                )
        ));
    }

    private void handleChat(RelayEnvelope relay) {
        ChatPayload chat = WireCodec.decodePayload(relay.getPayload(), ChatPayload.class);
        log.info("💬 Offline Mesh Chat from {} ({}): {}", relay.getSenderId(), chat.senderName(), chat.body());

        eventPublisher.publishEvent(CityEventMessage.of(
                "MESH_CHAT_RECEIVED",
                relay.getId(),
                Map.of(
                        "id", relay.getId(),
                        "senderId", relay.getSenderId(),
                        "recipientId", relay.getRecipientId() != null ? relay.getRecipientId() : "ALL",
                        "chat", chat,
                        "sentAt", relay.getSentAt()
                )
        ));
    }

    private ObservationType mapEmergencyToObservationType(String emergencyType) {
        if (emergencyType == null) return ObservationType.CRASH;
        return switch (emergencyType.toUpperCase()) {
            case "FLOOD", "WATER_LOGGING" -> ObservationType.FLOOD;
            case "COLLISION", "ACCIDENT", "CRASH" -> ObservationType.CRASH;
            case "CONGESTION", "STAMPEDE" -> ObservationType.CONGESTION;
            default -> ObservationType.CRASH;
        };
    }

    private ObservationType mapFieldReportToObservationType(String reportType) {
        if (reportType == null) return ObservationType.COMPLAINT;
        return switch (reportType.toUpperCase()) {
            case "FLOOD", "WATER_LOGGING" -> ObservationType.FLOOD;
            case "CRASH", "ACCIDENT" -> ObservationType.CRASH;
            case "CONGESTION", "ROAD_BLOCK" -> ObservationType.CONGESTION;
            case "RAIN" -> ObservationType.RAIN;
            default -> ObservationType.COMPLAINT;
        };
    }
}
