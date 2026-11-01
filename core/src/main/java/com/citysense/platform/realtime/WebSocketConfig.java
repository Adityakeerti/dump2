package com.citysense.platform.realtime;

import com.citysense.common.config.CitySenseProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    public static final String CITY_EVENTS_TOPIC = "/topic/city-events";

    private final String[] allowedOrigins;

    public WebSocketConfig(CitySenseProperties props) {
        this.allowedOrigins = props.security().corsAllowedOrigins().split(",");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic");
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Plain WebSocket for React Native and @stomp/stompjs; SockJS fallback for older browsers.
        registry.addEndpoint("/ws").setAllowedOriginPatterns(allowedOrigins);
        registry.addEndpoint("/ws-sockjs").setAllowedOriginPatterns(allowedOrigins).withSockJS();
    }
}
