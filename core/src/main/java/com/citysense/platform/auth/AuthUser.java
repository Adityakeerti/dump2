package com.citysense.platform.auth;

import java.util.UUID;

/** Authenticated principal built from JWT claims, so requests need no user lookup. */
public record AuthUser(UUID id, String email, Role role, boolean emailVerified) {}
