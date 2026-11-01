package com.citysense.directory;

import com.citysense.civic.CityEvent;
import com.citysense.civic.CityEventRepository;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Upserts the city directory (businesses) and real-world events from JSON resources, keyed by seed_key.
 * Every row carries the source URL it was verified against. Disable with SEED_DIRECTORY=false.
 */
@Component
public class CityDirectorySeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(CityDirectorySeeder.class);
    private static final ZoneId CITY_ZONE = ZoneId.of("Asia/Kolkata");

    @JsonIgnoreProperties(ignoreUnknown = true)
    record SeedBusiness(String key, String name, String category, String locality, String description,
                        double latitude, double longitude, String coordsPrecision, String sourceUrl) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record SeedEvent(String key, String title, String startsOn, String endsOn, String venue, String city,
                     String organizer, String category, String description, double latitude, double longitude,
                     String sourceUrl) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record BusinessFile(List<SeedBusiness> businesses) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EventFile(List<SeedEvent> events) {}

    private final BusinessRepository businesses;
    private final CityEventRepository events;
    private final ResourceLoader resources;
    private final ObjectMapper json;
    private final boolean enabled;

    public CityDirectorySeeder(BusinessRepository businesses, CityEventRepository events, ResourceLoader resources,
                               ObjectMapper json, @Value("${citysense.directory.seed-enabled:true}") boolean enabled) {
        this.businesses = businesses;
        this.events = events;
        this.resources = resources;
        this.json = json;
        this.enabled = enabled;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) throws Exception {
        if (!enabled) {
            return;
        }
        var bizRes = resources.getResource("classpath:seed/businesses.json");
        if (bizRes.exists()) {
            try (InputStream in = bizRes.getInputStream()) {
                List<SeedBusiness> list = json.readValue(in, BusinessFile.class).businesses();
                for (SeedBusiness s : list) {
                    Business b = businesses.findBySeedKey(s.key()).orElseGet(() -> new Business(s.key()));
                    b.apply(s.name(), s.category(), s.locality(), s.description(), s.latitude(), s.longitude(),
                            s.coordsPrecision(), s.sourceUrl());
                    businesses.save(b);
                }
                log.info("Seeded {} businesses", list.size());
            }
        }
        var evRes = resources.getResource("classpath:seed/events.json");
        if (evRes.exists()) {
            try (InputStream in = evRes.getInputStream()) {
                List<SeedEvent> list = json.readValue(in, EventFile.class).events();
                for (SeedEvent s : list) {
                    CityEvent e = events.findBySeedKey(s.key()).orElseGet(CityEvent::new);
                    var start = LocalDate.parse(s.startsOn()).atTime(10, 0).atZone(CITY_ZONE).toInstant();
                    var end = s.endsOn() == null || s.endsOn().isBlank() ? null
                            : LocalDate.parse(s.endsOn()).atTime(20, 0).atZone(CITY_ZONE).toInstant();
                    String venue = s.venue() == null ? s.city() : (s.city() == null || s.venue().contains(s.city())
                            ? s.venue() : s.venue() + ", " + s.city());
                    e.applySeed(s.key(), s.title(), s.description(), s.category(), s.latitude(), s.longitude(),
                            start, end, venue, s.organizer(), s.sourceUrl());
                    events.save(e);
                }
                log.info("Seeded {} city events", list.size());
            }
        }
    }
}
