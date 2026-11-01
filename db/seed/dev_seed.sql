-- Dev-only sample data (NOT a Flyway migration). Apply manually after V1:
--   docker exec -i citysense-db psql -U citysense -d citysense < db/seed/dev_seed.sql
-- Five Dehradun observations; the first three are within ~500m of Clock Tower
-- (30.3243, 78.0418) so they should correlate into one cluster.

INSERT INTO observations (type, latitude, longitude, observed_at, source, confidence, status, payload) VALUES
  ('cv_density', 30.3243, 78.0418, now() - interval '5 minutes',  'cam-clocktower-01', 0.92, 'VERIFIED',   '{"vehicles_per_min": 84, "camera": "clocktower-n"}'),
  ('complaint',  30.3260, 78.0430, now() - interval '8 minutes',  'citizen-app',       0.70, 'UNVERIFIED', '{"text": "Traffic jam near Clock Tower, not moving", "lang": "en"}'),
  ('congestion', 30.3230, 78.0400, now() - interval '3 minutes',  'sim-traffic',       0.85, 'SIMULATED',  '{"speed_kmph": 6}'),
  ('rain',       30.3165, 78.0322, now() - interval '20 minutes', 'imd-feed',          0.95, 'VERIFIED',   '{"mm_per_hr": 18}'),
  ('flood',      30.3400, 78.0600, now() - interval '12 minutes', 'citizen-app',       0.60, 'UNVERIFIED', '{"text": "Waterlogging on Rajpur Road", "depth_cm": 30}');
