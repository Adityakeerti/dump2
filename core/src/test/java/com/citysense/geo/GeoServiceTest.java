package com.citysense.geo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.citysense.common.error.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class GeoServiceTest {

    private static GeoProperties props(String publicBase) {
        return new GeoProperties("https://tiles.example/{z}/{x}/{y}.png", "© OSM", "https://nom.example",
                "https://osrm.example", "UA", publicBase, 3, 19, 10, 60, 10, 0, 5,
                30.0, 78.0, 13, 2500, "in");
    }

    @Test
    void tileCoordinatesAreBoundedByZoom() {
        assertThatCode(() -> GeoService.validateTile(3, 7, 7, 3, 19)).doesNotThrowAnyException();
        assertThatThrownBy(() -> GeoService.validateTile(3, 8, 0, 3, 19)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> GeoService.validateTile(2, 0, 0, 3, 19)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> GeoService.validateTile(20, 0, 0, 3, 19)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> GeoService.validateTile(5, -1, 0, 3, 19)).isInstanceOf(ApiException.class);
    }

    @Test
    @SuppressWarnings("unchecked")
    void styleTilesPointAtTheProxyNotTheProvider() {
        GeoService geo = new GeoService(props(""), new ObjectMapper());
        Map<String, Object> style = geo.style("http://10.0.2.2:8080/");
        Map<String, Object> osm = (Map<String, Object>) ((Map<String, Object>) style.get("sources")).get("osm");
        assertThat((List<String>) osm.get("tiles"))
                .containsExactly("http://10.0.2.2:8080/api/geo/tiles/{z}/{x}/{y}.png");
        assertThat(osm.get("attribution")).isEqualTo("© OSM");
    }

    @Test
    @SuppressWarnings("unchecked")
    void publicBaseUrlOverridesRequestHost() {
        GeoService geo = new GeoService(props("https://api.citysense.example"), new ObjectMapper());
        Map<String, Object> osm = (Map<String, Object>) ((Map<String, Object>) geo.style("http://internal:8080")
                .get("sources")).get("osm");
        assertThat((List<String>) osm.get("tiles")).first().asString().startsWith("https://api.citysense.example/");
    }

    @Test
    void routeRejectsUnknownProfileBeforeCallingUpstream() {
        GeoService geo = new GeoService(props(""), new ObjectMapper());
        assertThatThrownBy(() -> geo.route(30, 78, 30.1, 78.1, "helicopter")).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> geo.route(95, 78, 30.1, 78.1, "driving")).isInstanceOf(ApiException.class);
    }
}
