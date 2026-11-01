# Verification record — 2026-10-20

## Performed in this workspace

- Python `.venv`: **3.11.9**.
- Dependencies installed inside that virtual environment. FastAPI/SQLModel/Alembic/Pydantic and PDF packages upgraded; exact direct versions are in requirements files.
- E5 real-model CPU smoke: `intfloat/multilingual-e5-small` produced **384 dimensions**, squared vector norm **1.0**, using the Hindi query `शहर की सेवाएं`. Initial download+load+encode took **281.75 seconds**. This is cold-start evidence, not a throughput benchmark. Model is now cached on this host; Docker has a separate cache volume.
- Sentence Transformers 3.3.1 import and `local_files_only` constructor parameter verified.
- Unit/API/provider tests use explicit demo hash embeddings or mocked providers. They are not a corpus-quality evaluation.
- PostgreSQL integration tests are included and explicitly skipped unless TEST_DATABASE_URL is supplied. This host has neither Docker nor PostgreSQL commands available, so migrations have not been executed against a live database here.
- Application startup smoke using the real cached E5 model: `/health` **200**; `/ready` **503** with `database:false, embedder:true`, confirming that readiness does not pretend the unavailable database is healthy.
- `python -m alembic upgrade head --sql` generated both migrations successfully without connecting to a database. This checks migration generation, not live PostgreSQL execution.

## Documentation checks

### Local inference

Source: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

The server documents OpenAI-compatible `/v1/chat/completions`, `/v1/models`, and function calling dependent on the chosen model/template. Base URL configuration therefore includes `/v1`. The model file/context size and actual tool reliability on your server are unverified. `LOCAL_TOOLS_ENABLED` defaults false.

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_local_model --base-url http://localhost:8080/v1 --model YOUR_MODEL_ALIAS
.\.venv\Scripts\python.exe -m scripts.verify_llm_providers local --tools
```

### Groq

Sources:
- https://console.groq.com/docs/openai
- https://console.groq.com/docs/speech-to-text

Confirmed by docs: OpenAI-compatible base `https://api.groq.com/openai/v1`; transcription path `/audio/transcriptions`; models `whisper-large-v3-turbo` and `whisper-large-v3`; m4a supported; published free-tier file size 25 MB. This service intentionally applies a smaller configurable 10 MB default. Compatibility is partial, so only the supported basic message/tool fields are sent.

Actual account quotas, Hindi recording quality, key validity, and selected chat model availability are **unverified**. Set PROVIDER_RPM to your account limits; model names are configurable. No paid-tier claim is made.

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_llm_providers groq
.\.venv\Scripts\python.exe -m scripts.verify_llm_providers groq --tools
.\.venv\Scripts\python.exe -m scripts.verify_stt_providers groq recording1.m4a recording2.m4a recording3.m4a recording4.m4a recording5.m4a
```

### Sarvam

Sources:
- https://docs.sarvam.ai/api-reference/chat/chat-completions-v1.md
- https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe

Docs now specify `/v1/chat/completions` with `sarvam-105b` / `sarvam-105b-conversations`, not the earlier assumed `sarvam-m`. The implementation uses configurable SARVAM_MODEL and sends bearer plus `api-subscription-key` for chat. STT uses `/speech-to-text`, `api-subscription-key`, multipart audio, `language_code`, and `transcript` output. Hindi/English and m4a are documented. `saaras:v3` remains configurable; newer models are account-dependent.

The docs describe pricing; perpetual free access is **not verified**. Sarvam is opt-in via a key. The service works without it using local inference. No live Sarvam calls have been made.

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_llm_providers sarvam
.\.venv\Scripts\python.exe -m scripts.verify_stt_providers sarvam recording1.m4a recording2.m4a recording3.m4a recording4.m4a recording5.m4a
```

### Embeddings

Sources:
- https://huggingface.co/intfloat/multilingual-e5-small/raw/main/config.json
- https://huggingface.co/intfloat/multilingual-e5-small/raw/main/sentence_bert_config.json

Config confirms hidden size 384 and max sequence length 512. Ingestion uses the real model tokenizer to budget chunks when E5 is selected; query/passage prefixes are applied. The explicit demo hash backend has its own embed_model identity; retrieval never mixes it with E5 vectors.

### Android / Expo

These require the team's client and device and are **not verified** by backend tests. Follow `scripts/verify_android_tts.md` and `scripts/verify_expo_streaming.md`. No Expo application is present in this component workspace. TTS remains on-device; backend STT availability does not imply that a Hindi TTS voice exists on the device.

## Known compatibility/operational notes

- Upgrading Starlette introduced a deprecated httpx TestClient backend. Installing the supported `httpx2` development dependency removed that warning; backend outbound HTTP still uses httpx as required.
- Hugging Face cache on this Windows host cannot use symlinks without Developer Mode/admin privileges. The real embedding smoke succeeded anyway, with a cache-space warning. Optional Xet acceleration is absent, so downloads used ordinary HTTP.
- Buffered SSE is implemented and documented; provider-token live streaming and interrupted partial-token persistence are not claimed.
- Remaining live checks: PostgreSQL migrations/tenant isolation/concurrent confirm tests; real adapter schemas; actual free quotas/data-retention terms; local-model tools/context/latency; five real Hindi recordings; Android networking/TTS/Expo.
