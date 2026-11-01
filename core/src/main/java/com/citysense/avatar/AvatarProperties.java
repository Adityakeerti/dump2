package com.citysense.avatar;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** imageBasePath: URL path (relative to the API base) where avatar images are served. */
@ConfigurationProperties(prefix = "citysense.avatars")
public record AvatarProperties(boolean seedEnabled, String seedLocation, String imageBasePath) {}
