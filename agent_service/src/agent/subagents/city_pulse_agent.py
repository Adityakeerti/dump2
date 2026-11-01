"""City Pulse specialist: sole caller of live city-data tools.

SOP: fetch_city_data (only the feeds the question needs, in parallel) -> format_briefing.
"""

import asyncio
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.subagents.base import BaseSubAgent, SubAgentResult
from src.agent.tool_registry import PULSE, call_tool
from src.auth.schemas import Principal

INTENTS = {
    "traffic": re.compile(r"traffic|jam|congestion|delay|ट्रैफिक|जाम", re.I),
    "weather": re.compile(r"weather|rain|flood|waterlog|underpass|मौसम|बारिश|जलभराव", re.I),
    "aqi": re.compile(r"\baqi\b|air quality|pollution|pm2\.?5|प्रदूषण|हवा", re.I),
    "water": re.compile(r"water supply|supply schedule|tap water|jal sansthan|पानी की आपूर्ति|पानी", re.I),
    "events": re.compile(r"event|festival|mela|town hall|कार्यक्रम|मेला", re.I),
    "alerts": re.compile(r"alert|advisor|warning|closure|अलर्ट|चेतावनी", re.I),
    "notices": re.compile(r"notice|announcement|circular|सूचना|नोटिस", re.I),
    "incidents": re.compile(r"incident|घटना", re.I),
}


def _area(message: str, kwargs: dict[str, Any]) -> str:
    return (kwargs.get("location") or "")[:200]


class CityPulseSpecialist(BaseSubAgent):
    name: str = PULSE
    description: str = "Specialist for real-time city alerts, upcoming public events, and citizen pulse briefings"

    async def execute(
        self,
        session: AsyncSession | None,
        principal: Principal,
        message: str,
        context: Any = None,
        language: str = "en",
        **kwargs: Any,
    ) -> SubAgentResult:
        execution_steps: list[str] = []
        trace = kwargs.get("trace")
        uid = principal.user_id

        # Step 1: fetch_city_data — only the feeds this question needs, in parallel
        execution_steps.append("fetch_city_data")
        if kwargs.get("feeds"):
            # The main agent asked for exact feeds (app control: "show notices", "upcoming events").
            wanted = set(kwargs["feeds"]) & set(INTENTS)
        else:
            wanted = {name for name, rx in INTENTS.items() if rx.search(message)}
            specific = wanted & {"traffic", "weather", "aqi", "water", "notices", "incidents"}
            if not specific:
                wanted |= {"alerts", "events"}  # general "what's happening" briefing
        area = _area(message, kwargs)
        query_str = (kwargs.get("query") or message)[:500]
        calls = {
            "alerts": ("get_active_alerts", {"query": query_str}),
            "events": ("get_events", {"query": query_str}),
            "traffic": ("get_traffic_density", {"corridor_id": area or None}),
            "weather": ("fetch_weather_inundation", {"area": area}),
            "aqi": ("get_air_quality_index", {"area": area}),
            "water": ("check_water_supply_schedule", {"area": area}),
            "notices": ("get_govt_notices", {"limit": 5}),
            "incidents": ("get_city_incidents", {"limit": 5}),
        }
        keys = [k for k in calls if k in wanted]
        results = await asyncio.gather(
            *(call_tool(PULSE, calls[k][0], calls[k][1], uid, trace) for k in keys), return_exceptions=True
        )
        feeds: dict[str, dict[str, Any]] = {
            k: (r.get("data") if isinstance(r, dict) and r.get("served") == "live" and isinstance(r.get("data"), dict) else r)
            for k, r in zip(keys, results)
            if isinstance(r, dict)
        }

        def items(key: str) -> list[dict[str, Any]]:
            res = feeds.get(key) or {}
            raw = res.get("items") if isinstance(res, dict) else None
            if raw is None and isinstance(res, list):
                raw = res
            return [i for i in (raw or []) if isinstance(i, dict)]

        alerts = items("alerts")
        events = items("events")

        def sample(key: str) -> str:
            """Heading suffix for feeds served from built-in demo data (no live city feed connected)."""
            f = feeds.get(key)
            return (" (डेमो सैंपल डेटा)" if language == "hi" else " (sample data)") if isinstance(f, dict) and f.get("simulated") else ""

        # Step 2: format_briefing
        execution_steps.append("format_briefing")

        if language == "hi":
            lines = [
                "# 🌆 देहरादून सिटी पल्स: लाइव नागरिक बुलेटिन",
                "",
            ]
            lines += self._specific_sections(feeds, "hi")
        if language == "hi" and "alerts" in wanted:
            lines.append("### 🚨 सक्रिय नागरिक चेतावनियाँ एवं अलर्ट (Active Alerts)" + sample("alerts"))
            if alerts:
                for a in alerts:
                    severity = a.get("severity", "INFO")
                    badge = a.get("badge") or severity
                    title = a.get("title", "सूचना")
                    loc = a.get("location", "देहरादून")
                    desc = a.get("description", "")
                    lines.append(f"- `[{badge}]` **{title}**")
                    lines.append(f"  • *स्थान:* {loc}")
                    if desc:
                        lines.append(f"  • *विवरण:* {desc}")
            else:
                lines.append("- वर्तमान में कोई सक्रिय अलर्ट नहीं है।")
            lines.append("")
        if language == "hi" and "events" in wanted:
            lines.append("### 📅 आगामी सार्वजनिक एवं नागरिक कार्यक्रम (Upcoming Events)" + sample("events"))
            if events:
                for e in events:
                    title = e.get("title", "कार्यक्रम")
                    date = e.get("date", "")
                    time_slot = e.get("time", "")
                    loc = e.get("location", "देहरादून")
                    desc = e.get("description", "")
                    lines.append(f"- 🗓️ **{date}** ({time_slot}) — **{title}**")
                    lines.append(f"  • *स्थान:* {loc}")
                    if desc:
                        lines.append(f"  • *विवरण:* {desc}")
            else:
                lines.append("- वर्तमान में कोई आगामी कार्यक्रम सूचीबद्ध नहीं है।")
            lines.append("")
        if wanted & {"alerts", "events"} and language == "hi":
            lines.append(f"📊 **सिटी पल्स स्थिति:** {len(alerts)} सक्रिय अलर्ट | {len(events)} आगामी नागरिक कार्यक्रम")

        if language != "hi":
            lines = [
                "# 🌆 Dehradun City Pulse: Live Briefing",
                "",
            ]
            lines += self._specific_sections(feeds, "en")
        if language != "hi" and "alerts" in wanted:
            lines.append("### 🚨 Active City Alerts & Advisories" + sample("alerts"))
            if alerts:
                for a in alerts:
                    severity = a.get("severity", "INFO")
                    badge = a.get("badge") or severity
                    title = a.get("title", "Alert")
                    loc = a.get("location", "Dehradun")
                    desc = a.get("description", "")
                    lines.append(f"- `[{badge}]` **{title}**")
                    lines.append(f"  • *Location:* {loc}")
                    if desc:
                        lines.append(f"  • *Details:* {desc}")
            else:
                lines.append("- No active emergency alerts at this time.")
            lines.append("")
        if language != "hi" and "events" in wanted:
            lines.append("### 📅 Upcoming Civic & Community Events" + sample("events"))
            if events:
                for e in events:
                    title = e.get("title", "Event")
                    date = e.get("date", "")
                    time_slot = e.get("time", "")
                    loc = e.get("location", "Dehradun")
                    desc = e.get("description", "")
                    lines.append(f"- 🗓️ **{date}** ({time_slot}) — **{title}**")
                    lines.append(f"  • *Venue:* {loc}")
                    if desc:
                        lines.append(f"  • *Overview:* {desc}")
            else:
                lines.append("- No public events scheduled for this window.")
            lines.append("")
        if wanted & {"alerts", "events"} and language != "hi":
            lines.append(f"📊 **Live Digest Status:** {len(alerts)} active alerts | {len(events)} upcoming civic events")

        if any(isinstance(f, dict) and f.get("simulated") for f in feeds.values()):
            lines.append(
                "_ℹ️ कुछ जानकारी डेमो सैंपल डेटा है (लाइव फ़ीड जुड़ा नहीं है)।_" if language == "hi"
                else "_ℹ️ Some items are demo sample data (no live city feed connected)._"
            )
        response_text = "\n".join(lines)

        return SubAgentResult(
            status="ANSWERED",
            response_text=response_text,
            sources=[],
            cta="view_alerts",
            execution_steps=execution_steps,
            metadata={
                "alerts_count": len(alerts),
                "events_count": len(events),
                "feeds": sorted(feeds),
                "sample_data": any(isinstance(f, dict) and f.get("simulated") for f in feeds.values()),
            },
        )

    @staticmethod
    def _specific_sections(feeds: dict[str, dict[str, Any]], lang: str) -> list[str]:
        hi = lang == "hi"
        out: list[str] = []
        t = feeds.get("traffic")
        if t:
            out += [
                "### 🚗 " + ("ट्रैफिक स्थिति" if hi else "Traffic Density")
                + ((" (डेमो सैंपल डेटा)" if hi else " (sample data)") if t.get("simulated") else ""),
                f"- {t.get('junction_id', '—')} | {t.get('corridor_id', '—')}: **{t.get('density_level', '—')}** "
                f"({t.get('average_speed_kmh', '—')} km/h, ~{t.get('wait_time_seconds', '—')}s wait)",
                f"- {'वैकल्पिक मार्ग' if hi else 'Suggested alternate'}: {t.get('recommended_alternate', '—')}",
                "",
            ]
        w = feeds.get("weather")
        if w:
            depth = w.get("water_depth_cm_estimate")
            out += [
                "### 🌧️ " + ("मौसम एवं जलभराव" if hi else "Weather & Underpass Inundation"),
                f"- {'वर्षा' if hi else 'Rainfall'}: {w.get('precipitation_mm', w.get('rain_mm', '—'))} mm · "
                f"{'अनुमानित जल स्तर' if hi else 'est. water depth'}: {depth if depth is not None else '—'} cm",
                f"- {'अंडरपास स्थिति' if hi else 'Underpass status'}: **{w.get('underpass_status', 'UNKNOWN')}**"
                + (f" — {w['advice']}" if w.get("advice") else ""),
                "",
            ]
        a = feeds.get("aqi")
        if a:
            out += [
                "### 🌫️ " + ("वायु गुणवत्ता" if hi else "Air Quality"),
                f"- AQI (US): **{a.get('us_aqi', '—')}** · PM2.5: {a.get('pm2_5', '—')} · PM10: {a.get('pm10', '—')}"
                + (f" — {a['advice']}" if a.get("advice") else ""),
                "",
            ]
        no = feeds.get("notices")
        if no is not None:
            rows = [n for n in (no.get("items") or []) if isinstance(n, dict)]
            out.append("### 📜 " + ("सरकारी सूचनाएँ" if hi else "Government Notices"))
            for n in rows[:5]:
                title = (n.get("hindiTitle") if hi and n.get("hindiTitle") else n.get("title")) or "Notice"
                out.append(f"- **{title}** — {n.get('department', '')} ({n.get('referenceNumber', '')})")
                if n.get("summary"):
                    out.append(f"  {str(n['summary'])[:180]}")
            if not rows:
                out.append("- " + ("अभी कोई सूचना प्रकाशित नहीं है।" if hi else "No notices published right now."))
            out.append("")
        inc = feeds.get("incidents")
        if inc is not None:
            rows = [i for i in (inc.get("items") or []) if isinstance(i, dict)]
            out.append("### 🚨 " + ("हाल की घटनाएँ" if hi else "Recent Incidents"))
            for i in rows[:5]:
                out.append(f"- **{i.get('type') or i.get('category') or 'Incident'}** · {i.get('status', '')} · "
                           f"{i.get('title') or i.get('description') or ''}"[:200])
            if not rows:
                out.append("- " + ("कोई हाल की घटना नहीं।" if hi else "No recent incidents."))
            out.append("")
        wa = feeds.get("water")
        if wa:
            out.append("### 🚰 " + ("जल आपूर्ति" if hi else "Water Supply"))
            for p in wa.get("passages", [])[:1]:
                out.append(f"- {p['excerpt'][:300]} *({p['title']})*")
            if wa.get("note"):
                out.append(f"- _{wa['note']}_")
            out.append("")
        return out
