package com.citysense.avatar;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Upserts avatars (by handle) from a JSON file. Disable with SEED_AVATARS=false. */
@Component
public class AvatarSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AvatarSeeder.class);

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record SeedAvatar(String handle, String name, String title, String category, String persona, String intro,
                             String pricing, String websiteUrl, String instagramUrl, String threadsUrl, String xUrl,
                             String pinImage, String heroImage, BigDecimal rating, int reviewCount,
                             double latitude, double longitude) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record SeedFile(List<SeedAvatar> avatars) {}

    private final AvatarRepository repo;
    private final AvatarProperties props;
    private final ResourceLoader resources;
    private final ObjectMapper json;

    public AvatarSeeder(AvatarRepository repo, AvatarProperties props, ResourceLoader resources, ObjectMapper json) {
        this.repo = repo;
        this.props = props;
        this.resources = resources;
        this.json = json;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) throws IOException {
        if (!props.seedEnabled()) {
            return;
        }
        var resource = resources.getResource(props.seedLocation());
        if (!resource.exists()) {
            log.warn("Avatar seed file {} not found; skipping", props.seedLocation());
            return;
        }
        SeedFile file;
        try (InputStream in = resource.getInputStream()) {
            file = json.readValue(in, SeedFile.class);
        }
        for (SeedAvatar s : file.avatars()) {
            Avatar a = repo.findByHandle(s.handle()).orElseGet(() -> new Avatar(s.handle()));
            a.apply(s);
            repo.save(a);
        }
        log.info("Seeded {} avatars from {}", file.avatars().size(), props.seedLocation());
    }
}
