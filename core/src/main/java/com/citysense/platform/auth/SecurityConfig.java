package com.citysense.platform.auth;

import com.citysense.common.config.CitySenseProperties;
import java.util.Arrays;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, JwtService jwtService, CitySenseProperties props)
            throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsSource(props)))
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.POST, "/api/auth/login", "/api/auth/register",
                                "/api/auth/otp/send", "/api/auth/otp/verify",
                                "/api/auth/password/forgot", "/api/auth/password/reset").permitAll()
                        // Map rendering: native tile requests carry no JWT. Lookups/routing stay authenticated.
                        .requestMatchers(HttpMethod.GET, "/api/geo/config", "/api/geo/style.json", "/api/geo/tiles/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/avatars/**").permitAll()
                        // Complaints are private: only the option lists and public city bulletins are open.
                        // Per-complaint ownership, roles and transitions are enforced in CivicController/CivicService.
                        .requestMatchers(HttpMethod.GET, "/api/complaints/meta", "/api/city-events", "/api/businesses").permitAll()
                        .requestMatchers("/api/complaints", "/api/complaints/**",
                                "/api/city-events", "/api/city-events/**").authenticated()
                        .requestMatchers("/ws/**", "/ws-sockjs/**").permitAll()
                        .requestMatchers("/v3/api-docs/**", "/v3/api-docs.yaml", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                        .requestMatchers("/actuator/health/**").permitAll()
                        .requestMatchers("/api/weather/**", "/api/mobility/**").permitAll()
                        .requestMatchers("/api/agent/**", "/api/mesh/**").permitAll()
                        // Denials forward to /error without re-running the JWT filter; keep 403s from becoming 401s.
                        .requestMatchers("/error", "/knit.apk", "/*.apk").permitAll()
                        .requestMatchers("/internal/**").hasRole("INTERNAL")
                        .requestMatchers("/api/audit/**", "/api/scenarios/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .exceptionHandling(e -> e.authenticationEntryPoint(new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
                .addFilterBefore(new InternalApiKeyFilter(props.security().internalApiKey()),
                        UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(new JwtAuthFilter(jwtService), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    private CorsConfigurationSource corsSource(CitySenseProperties props) {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOriginPatterns(Arrays.asList(props.security().corsAllowedOrigins().split(",")));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
