"""Polite Refusal and Civic Guidance module for City Sense Agent Service.

Constructs courteous, structured refusals, boundary acknowledgments, and warm civic greetings
equipped with action chips (CTAs) instead of robotic abstention responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from src.agent.guardrails.scope_classifier import QueryScope
from src.agent.schemas import AgentInfo, AgentResponse


@dataclass
class ActionChip:
    """Actionable quick-action chip / CTA presented to citizens."""

    id: str
    label: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "action": self.action,
        }


# Standard English Action Chips
ACTION_CHIPS_EN: dict[str, ActionChip] = {
    "report_issue": ActionChip(
        id="report_issue",
        label="Report Civic Issue",
        action="report_issue",
    ),
    "view_alerts": ActionChip(
        id="view_alerts",
        label="View City Alerts & Traffic",
        action="view_alerts",
    ),
    "explore_schemes": ActionChip(
        id="explore_schemes",
        label="Explore Municipal Schemes",
        action="explore_schemes",
    ),
    "emergency_helplines": ActionChip(
        id="emergency_helplines",
        label="Emergency Helplines (112 / 108)",
        action="emergency_helplines",
    ),
}

# Standard Hindi Action Chips
ACTION_CHIPS_HI: dict[str, ActionChip] = {
    "report_issue": ActionChip(
        id="report_issue",
        label="नागरिक शिकायत दर्ज करें",
        action="report_issue",
    ),
    "view_alerts": ActionChip(
        id="view_alerts",
        label="शहर अलर्ट व ट्रैफिक देखें",
        action="view_alerts",
    ),
    "explore_schemes": ActionChip(
        id="explore_schemes",
        label="नगर निगम योजनाएं देखें",
        action="explore_schemes",
    ),
    "emergency_helplines": ActionChip(
        id="emergency_helplines",
        label="आपातकालीन हेल्पलाइन (112 / 108)",
        action="emergency_helplines",
    ),
}


@dataclass
class PoliteRefusalResult:
    """Structured response containing user message, action chips, and metadata."""

    message: str
    scope: QueryScope
    action_chips: list[ActionChip] = field(default_factory=list)
    suggested_cta: str | None = None
    language: str = "en"
    detected_topic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "scope": self.scope.value,
            "action_chips": [c.to_dict() for c in self.action_chips],
            "suggested_cta": self.suggested_cta,
            "language": self.language,
            "detected_topic": self.detected_topic,
        }

    def to_agent_response(
        self,
        session_id: UUID | None = None,
        message_id: UUID | None = None,
        agent_id: str = "general",
        agent_name: str = "City Sense",
    ) -> AgentResponse:
        """Converts this refusal into the standard Pydantic AgentResponse contract."""
        status = "ANSWERED" if self.scope == QueryScope.CIVIC_GREETING else "ABSTAINED"
        return AgentResponse(
            sessionId=session_id or uuid4(),
            messageId=message_id or uuid4(),
            status=status,
            answer=self.message,
            agent=AgentInfo(id=agent_id, name=agent_name),
            sources=[],
            cta=self.suggested_cta,
            served="fallback",
        )


def refuse_injection(language: str = "en") -> PoliteRefusalResult:
    """Generates a firm, courteous boundary acknowledgment redirecting to civic features."""
    is_hindi = language == "hi"
    chips_dict = ACTION_CHIPS_HI if is_hindi else ACTION_CHIPS_EN

    if is_hindi:
        message = (
            "मैं सिटी सेंस (City Sense) हूँ, आपके शहर का समर्पित नागरिक एआई सहायक। "
            "मैं नगर निगम सुरक्षा मानकों के अधीन कार्य करता हूँ और सिस्टम निर्देशों को बदलने, "
            "सुरक्षा सीमाओं को हटाने अथवा आंतरिक कॉन्फ़िगरेशन साझा करने में असमर्थ हूँ।\n\n"
            "मैं शहर की सत्यापित नागरिक सेवाओं, शिकायतों के निवारण, आपातकालीन संपर्कों और "
            "नगर निगम योजनाओं में आपकी सहायता के लिए तैयार हूँ। कृपया बताएँ कि मैं शहर संबंधी कार्यों में "
            "आपकी क्या मदद कर सकता हूँ?"
        )
    else:
        message = (
            "I am City Sense, your dedicated civic AI assistant. "
            "I operate within municipal safety guidelines and cannot bypass system instructions, "
            "alter security boundaries, or reveal internal configurations.\n\n"
            "I am here to assist you with verified city services, reporting civic complaints, "
            "emergency contacts, and municipal welfare schemes. Please let me know how I can help you with our city today."
        )

    action_chips = [
        chips_dict["report_issue"],
        chips_dict["view_alerts"],
        chips_dict["explore_schemes"],
    ]

    return PoliteRefusalResult(
        message=message,
        scope=QueryScope.INJECTION,
        action_chips=action_chips,
        suggested_cta="report_issue",
        language=language,
        detected_topic="prompt_injection",
    )


def refuse_out_of_scope(
    topic: str | None = None,
    language: str = "en",
) -> PoliteRefusalResult:
    """Generates a friendly, courteous explanation of City Sense scope with action chips."""
    is_hindi = language == "hi"
    chips_dict = ACTION_CHIPS_HI if is_hindi else ACTION_CHIPS_EN

    # Map detected topic to clean description
    topic_clean = topic or "non-civic inquiries"

    if is_hindi:
        hindi_topic_map = {
            "coding and software engineering": "कोडिंग व प्रोग्रामिंग",
            "mathematical calculations": "गणित के सवालों व गणना",
            "cooking recipes": "खाना पकाने की विधि व रेसिपी",
            "general trivia, creative writing, or entertainment": "मनोरंजन, कविता या सामान्य ज्ञान",
            "non-civic general inquiry": "नगर निगम से इतर सामान्य प्रश्नों",
        }
        topic_display = hindi_topic_map.get(topic_clean, "इस विषय")
        message = (
            f"मैं सिटी सेंस (City Sense) हूँ, आपके शहर का नागरिक सहायक। "
            f"यद्यपि मैं {topic_display} में सहायता नहीं कर सकता, परंतु मैं नागरिक समस्याओं, "
            f"शहर के अलर्ट, नगर निगम योजनाओं और आपातकालीन रूटिंग में आपकी पूरी मदद कर सकता हूँ।\n\n"
            f"आप मुझसे निम्न कार्यों में सहायता ले सकते हैं:\n"
            f"- सड़क के गड्ढे, कूड़ा या स्ट्रीट लाइट जैसी समस्याओं की शिकायत दर्ज करना\n"
            f"- शहर के लाइव अलर्ट, ट्रैफिक और आपातकालीन संपर्क प्राप्त करना\n"
            f"- जन्म/मृत्यु प्रमाण पत्र, हाउस टैक्स या नगर निगम योजनाओं की जानकारी लेना"
        )
    else:
        message = (
            f"I am City Sense, your civic assistant for the city. "
            f"While I cannot help with {topic_clean}, I can help you with civic issues, "
            f"city alerts, municipal schemes, and emergency routing.\n\n"
            f"Here are some of the ways I can assist you:\n"
            f"- Report civic problems like potholes, garbage accumulation, or defective streetlights\n"
            f"- Check live city alerts, road conditions, and traffic updates\n"
            f"- Explore municipal welfare schemes, citizen certificates, and property tax procedures"
        )

    action_chips = [
        chips_dict["report_issue"],
        chips_dict["view_alerts"],
        chips_dict["explore_schemes"],
    ]

    return PoliteRefusalResult(
        message=message,
        scope=QueryScope.OUT_OF_SCOPE,
        action_chips=action_chips,
        suggested_cta="report_issue",
        language=language,
        detected_topic=topic_clean,
    )


def respond_civic_greeting(language: str = "en") -> PoliteRefusalResult:
    """Generates a warm introduction to City Sense with suggested quick actions."""
    is_hindi = language == "hi"
    chips_dict = ACTION_CHIPS_HI if is_hindi else ACTION_CHIPS_EN

    if is_hindi:
        message = (
            "नमस्ते! मैं सिटी सेंस (City Sense) हूँ, आपके शहर का समर्पित नागरिक एआई सहायक। "
            "मैं नगर निगम सेवाओं, नागरिक शिकायतों के समाधान (जैसे सड़क के गड्ढे, स्ट्रीट लाइट या सफाई), "
            "सरकारी योजनाओं की जानकारी और लाइव शहर अलर्ट में आपकी सहायता के लिए उपस्थित हूँ।\n\n"
            "आज मैं आपकी क्या सहायता कर सकता हूँ? आप नीचे दिए गए त्वरित विकल्पों में से चुन सकते हैं या सीधे अपना प्रश्न पूछ सकते हैं:"
        )
    else:
        message = (
            "Namaste! I am City Sense, your dedicated civic AI assistant for the city. "
            "I am here to help you navigate municipal services, report local civic issues "
            "(such as potholes, streetlights, or waste management), check real-time city alerts, "
            "and access citizen welfare schemes.\n\n"
            "How can I help you today? You can choose one of the quick actions below or ask a question directly:"
        )

    action_chips = [
        chips_dict["report_issue"],
        chips_dict["view_alerts"],
        chips_dict["explore_schemes"],
        chips_dict["emergency_helplines"],
    ]

    return PoliteRefusalResult(
        message=message,
        scope=QueryScope.CIVIC_GREETING,
        action_chips=action_chips,
        suggested_cta="report_issue",
        language=language,
        detected_topic="civic_greeting",
    )


def build_polite_refusal(
    scope: QueryScope,
    language: str = "en",
    detected_topic: str | None = None,
) -> PoliteRefusalResult:
    """Builds an appropriate courteous structured response based on the query scope."""
    if scope == QueryScope.INJECTION:
        return refuse_injection(language=language)
    elif scope == QueryScope.CIVIC_GREETING:
        return respond_civic_greeting(language=language)
    else:
        # Default for OUT_OF_SCOPE or unhandled scopes needing polite redirection
        return refuse_out_of_scope(topic=detected_topic, language=language)
