package com.citysense.avatar;

import com.citysense.avatar.AvatarDtos.AvatarChatRequest;
import com.citysense.avatar.AvatarDtos.AvatarChatResponse;
import com.citysense.avatar.AvatarDtos.AvatarView;
import com.citysense.avatar.AvatarDtos.ToggleResponse;
import com.citysense.platform.auth.AuthUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/avatars")
@Tag(name = "Avatars", description = "City service avatars on the Explore map (requires a verified account)")
public class AvatarController {

    private final AvatarService service;

    public AvatarController(AvatarService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "Avatars near a point (lat/lng/radiusMeters) or everywhere; q searches name/title/category")
    public List<AvatarView> list(@AuthenticationPrincipal AuthUser user,
                                 @RequestParam(required = false) Double lat,
                                 @RequestParam(required = false) Double lng,
                                 @RequestParam(required = false) Double radiusMeters,
                                 @RequestParam(required = false) String q) {
        return service.list(user, lat, lng, radiusMeters, q);
    }

    @GetMapping("/saved")
    @Operation(summary = "Avatars the current user saved, newest first")
    public List<AvatarView> saved(@AuthenticationPrincipal AuthUser user) {
        return service.saved(user);
    }

    @GetMapping("/{id}")
    public AvatarView get(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id) {
        return service.get(user, id);
    }

    @PutMapping("/{id}/save")
    public ToggleResponse save(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id) {
        return service.setSaved(user, id, true);
    }

    @DeleteMapping("/{id}/save")
    public ToggleResponse unsave(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id) {
        return service.setSaved(user, id, false);
    }

    @PutMapping("/{id}/like")
    public ToggleResponse like(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id) {
        return service.setLiked(user, id, true);
    }

    @DeleteMapping("/{id}/like")
    public ToggleResponse unlike(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id) {
        return service.setLiked(user, id, false);
    }

    @PostMapping("/{id}/chat")
    @Operation(summary = "Chat with an avatar: quick intents (INTRO, PRICING, WEBSITE) or free text to its persona")
    public AvatarChatResponse chat(@AuthenticationPrincipal AuthUser user, @PathVariable UUID id,
                                   @Valid @RequestBody AvatarChatRequest req) {
        return service.chat(user, id, req);
    }
}
