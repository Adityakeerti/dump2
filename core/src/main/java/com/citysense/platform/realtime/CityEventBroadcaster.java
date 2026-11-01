package com.citysense.platform.realtime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * Services publish CityEventMessage as a Spring application event; it is pushed to STOMP only
 * after the transaction commits, so clients never see data that was rolled back.
 * The topic has no subscription auth yet, so every message passes through {@link LiveEventRedactor}.
 */
@Component
public class CityEventBroadcaster {

    private static final Logger log = LoggerFactory.getLogger(CityEventBroadcaster.class);

    private final SimpMessagingTemplate messaging;
    private final LiveEventRedactor redactor;

    public CityEventBroadcaster(SimpMessagingTemplate messaging, LiveEventRedactor redactor) {
        this.messaging = messaging;
        this.redactor = redactor;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT, fallbackExecution = true)
    public void onCityEvent(CityEventMessage message) {
        try {
            messaging.convertAndSend(WebSocketConfig.CITY_EVENTS_TOPIC, redactor.redact(message));
        } catch (RuntimeException e) {
            // Broadcast is best-effort: the data is committed and clients can re-fetch over REST.
            log.warn("Failed to broadcast {} {}: {}", message.type(), message.entityId(), e.getMessage());
        }
    }
}
