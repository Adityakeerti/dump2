package com.citysense.avatar;

import com.citysense.agent.AgentDtos;
import com.citysense.agent.AgentResponder;
import com.citysense.avatar.AvatarDtos.AvatarChatRequest;
import com.citysense.avatar.AvatarDtos.AvatarChatResponse;
import com.citysense.avatar.AvatarDtos.AvatarView;
import com.citysense.avatar.AvatarDtos.ChatIntent;
import com.citysense.avatar.AvatarDtos.Socials;
import com.citysense.avatar.AvatarDtos.ToggleResponse;
import com.citysense.common.error.ApiException;
import com.citysense.geo.GeoProperties;
import com.citysense.platform.auth.AuthUser;
import java.time.Instant;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AvatarService {

    private static final int MAX_RESULTS = 100;

    private final AvatarRepository avatars;
    private final NamedParameterJdbcTemplate jdbc;
    private final AgentResponder agent;
    private final GeoProperties geo;
    private final String imageBasePath;

    public AvatarService(AvatarRepository avatars, NamedParameterJdbcTemplate jdbc, AgentResponder agent,
                         GeoProperties geo, AvatarProperties props) {
        this.avatars = avatars;
        this.jdbc = jdbc;
        this.agent = agent;
        this.geo = geo;
        this.imageBasePath = props.imageBasePath().replaceAll("/+$", "");
    }

    @Transactional(readOnly = true)
    public List<AvatarView> list(AuthUser user, Double lat, Double lng, Double radiusMeters, String query) {
        requireVerified(user);
        String q = query == null || query.isBlank() ? null : "%" + query.trim() + "%";
        List<Avatar> found;
        if (lat != null && lng != null) {
            double radius = radiusMeters != null && radiusMeters > 0 ? radiusMeters : geo.geofenceRadiusMeters();
            found = avatars.findNearby(lat, lng, radius, q, MAX_RESULTS);
        } else {
            found = avatars.search(q, MAX_RESULTS);
        }
        return views(user, found, lat, lng);
    }

    @Transactional(readOnly = true)
    public AvatarView get(AuthUser user, UUID id) {
        requireVerified(user);
        return views(user, List.of(load(id)), null, null).get(0);
    }

    @Transactional(readOnly = true)
    public List<AvatarView> saved(AuthUser user) {
        requireVerified(user);
        List<UUID> ids = jdbc.queryForList(
                "SELECT avatar_id FROM avatar_saves WHERE user_id = :u ORDER BY created_at DESC",
                Map.of("u", user.id()), UUID.class);
        Map<UUID, Avatar> byId = avatars.findAllById(ids).stream()
                .filter(Avatar::isActive)
                .collect(Collectors.toMap(Avatar::getId, a -> a));
        return views(user, ids.stream().filter(byId::containsKey).map(byId::get).toList(), null, null);
    }

    @Transactional
    public ToggleResponse setSaved(AuthUser user, UUID id, boolean saved) {
        return toggle(user, id, saved, "avatar_saves");
    }

    @Transactional
    public ToggleResponse setLiked(AuthUser user, UUID id, boolean liked) {
        return toggle(user, id, liked, "avatar_likes");
    }

    /**
     * Quick-prompt intents are answered from the avatar's own record so they never drift from the
     * data shown on screen; free text goes to the avatar's agent persona.
     */
    // Not @Transactional: the agent call can take seconds and must not hold a pooled DB connection.
    public AvatarChatResponse chat(AuthUser user, UUID id, AvatarChatRequest req) {
        requireVerified(user);
        Avatar a = load(id);
        String lang = req.language() == null ? "en" : req.language();
        String session = req.sessionId() == null || req.sessionId().isBlank()
                ? UUID.randomUUID().toString() : req.sessionId();
        if (req.intent() != null) {
            return switch (req.intent()) {
                case INTRO -> answer(session, a.getIntro(), ChatIntent.INTRO, null);
                case PRICING -> answer(session, a.getPricing() != null ? a.getPricing()
                        : a.getName() + " has not published pricing yet.", ChatIntent.PRICING, null);
                case WEBSITE -> a.getWebsiteUrl() != null
                        ? answer(session, "Here is the official website for " + a.getName() + ".",
                                ChatIntent.WEBSITE, a.getWebsiteUrl())
                        : answer(session, a.getName() + " has no official website listed.", ChatIntent.WEBSITE, null);
            };
        }
        if (req.message() == null || req.message().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Provide a message or an intent");
        }
        // Only forward a client-held session id; a fresh conversation lets the agent mint one.
        String clientSession = req.sessionId() == null || req.sessionId().isBlank() ? null : req.sessionId();
        // The avatar answers as a local area agent; agent_service hands emergencies/complaints to the main agent.
        AgentDtos.ChatResponse r = agent.respondLocal(
                new AgentDtos.LocalAvatar(a.getHandle(), a.getName(), a.getTitle(), a.getPersona(), a.getCategory(),
                        a.getIntro(), a.getLatitude(), a.getLongitude()),
                new AgentDtos.ChatRequest(req.message(), a.getPersona(), lang, clientSession, req.latitude(),
                        req.longitude()));
        return new AvatarChatResponse(r.sessionId(), r.reply(), null, null, r.sources(), r.timestamp(),
                r.status(), r.plan(), r.pendingAction(), r.actionData());
    }

    private AvatarChatResponse answer(String session, String text, ChatIntent intent, String link) {
        return new AvatarChatResponse(session, text, intent, link, List.of(), Instant.now(), "ANSWERED",
                null, null, null);
    }

    private ToggleResponse toggle(AuthUser user, UUID id, boolean on, String table) {
        requireVerified(user);
        load(id);
        var params = new MapSqlParameterSource().addValue("u", user.id()).addValue("a", id);
        // Table names come from the two callers above, never from input.
        if (on) {
            jdbc.update("INSERT INTO " + table + " (user_id, avatar_id) VALUES (:u, :a) ON CONFLICT DO NOTHING", params);
        } else {
            jdbc.update("DELETE FROM " + table + " WHERE user_id = :u AND avatar_id = :a", params);
        }
        Long count = jdbc.queryForObject("SELECT count(*) FROM " + table + " WHERE avatar_id = :a", params, Long.class);
        return new ToggleResponse(id, on, count == null ? 0 : count);
    }

    private Avatar load(UUID id) {
        return avatars.findByIdAndActiveTrue(id).orElseThrow(() -> ApiException.notFound("Avatar", id));
    }

    private List<AvatarView> views(AuthUser user, List<Avatar> list, Double lat, Double lng) {
        if (list.isEmpty()) {
            return List.of();
        }
        List<UUID> ids = list.stream().map(Avatar::getId).toList();
        Set<UUID> saved = idsFor("avatar_saves", user.id(), ids);
        Set<UUID> liked = idsFor("avatar_likes", user.id(), ids);
        Map<UUID, Long> likeCounts = new java.util.HashMap<>();
        jdbc.query("SELECT avatar_id, count(*) AS c FROM avatar_likes WHERE avatar_id IN (:ids) GROUP BY avatar_id",
                Map.of("ids", ids), rs -> {
                    likeCounts.put(rs.getObject("avatar_id", UUID.class), rs.getLong("c"));
                });
        return list.stream().map(a -> new AvatarView(
                a.getId(), a.getHandle(), a.getName(), a.getTitle(), a.getCategory(), a.getPersona(),
                a.getIntro(), a.getPricing(), a.getWebsiteUrl(),
                new Socials(a.getInstagramUrl(), a.getThreadsUrl(), a.getXUrl()),
                imageBasePath + "/" + a.getPinImage(), imageBasePath + "/" + a.getHeroImage(),
                a.getRating(), a.getReviewCount(), likeCounts.getOrDefault(a.getId(), 0L),
                a.getLatitude(), a.getLongitude(),
                lat != null && lng != null ? haversineMeters(lat, lng, a.getLatitude(), a.getLongitude()) : null,
                saved.contains(a.getId()), liked.contains(a.getId()))).toList();
    }

    private Set<UUID> idsFor(String table, UUID userId, Collection<UUID> avatarIds) {
        return new HashSet<>(jdbc.queryForList(
                "SELECT avatar_id FROM " + table + " WHERE user_id = :u AND avatar_id IN (:ids)",
                Map.of("u", userId, "ids", avatarIds), UUID.class));
    }

    static void requireVerified(AuthUser user) {
        if (user == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Sign in required");
        }
        if (!user.emailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Verify your email to continue");
        }
    }

    static double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
        double r = 6_371_000d;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double h = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 2 * r * Math.asin(Math.sqrt(h));
    }
}
