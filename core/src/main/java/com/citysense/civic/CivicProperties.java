package com.citysense.civic;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Civic vocabulary served to clients so they never hard-code it. escalationLadder[i] names
 * escalation level i (0 = just filed). priorities must match the complaints.priority CHECK.
 */
@ConfigurationProperties(prefix = "citysense.civic")
public record CivicProperties(List<String> priorities, List<String> escalationLadder) {}
