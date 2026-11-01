package com.citysense.platform.incident;

import com.citysense.platform.action.ActionType;
import com.citysense.platform.action.AgentActionService;
import com.citysense.platform.action.AgentActionService.Proposal;
import com.citysense.platform.observation.Observation;
import com.citysense.platform.observation.ObservationType;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * Turns an incident's linked observations into proposed AgentActions. High-impact proposals
 * land in the approval queue; only low-risk notifications auto-execute.
 */
@Component
public class CoordinatorRules {

    static final String AGENT = "coordinator";

    private final AgentActionService actions;

    public CoordinatorRules(AgentActionService actions) {
        this.actions = actions;
    }

    public void evaluate(Incident incident, List<Observation> members) {
        Set<ObservationType> types = members.stream().map(Observation::getType)
                .collect(Collectors.toCollection(() -> EnumSet.noneOf(ObservationType.class)));
        for (Proposal p : proposalsFor(incident, types)) {
            actions.proposeOnce(p);
        }
    }

    static List<Proposal> proposalsFor(Incident incident, Set<ObservationType> types) {
        var out = new java.util.ArrayList<Proposal>();
        Map<String, Object> where = Map.of(
                "incidentTitle", incident.getTitle(),
                "latitude", incident.getLatitude(),
                "longitude", incident.getLongitude());

        if (types.contains(ObservationType.FLOOD)) {
            out.add(proposal(incident, ActionType.ROAD_CLOSURE, "Close roads around " + incident.getTitle(), where));
        }
        if (types.contains(ObservationType.CRASH)) {
            out.add(proposal(incident, ActionType.DISPATCH, "Dispatch ambulance to " + incident.getTitle(), where));
        }
        if (types.contains(ObservationType.FLOOD) && incident.getSeverity() >= 5) {
            out.add(proposal(incident, ActionType.EVACUATION, "Evacuate area around " + incident.getTitle(), where));
        }
        if (incident.getSeverity() >= 3) {
            out.add(proposal(incident, ActionType.NOTIFY_CITIZENS,
                    "Warn citizens near " + incident.getTitle(), where));
        }
        return out;
    }

    private static Proposal proposal(Incident incident, ActionType type, String summary, Map<String, Object> payload) {
        return new Proposal(incident.getId(), AGENT, type, null, summary, payload);
    }
}
