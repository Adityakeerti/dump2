"""Script to probe all available models in Groq and Ollama Cloud,

test which ones are free (not 402/quota blocked),
and check image/vision capability for each working model.
"""

import os
import sys
import json
import base64
import io
import time
import httpx
from dotenv import load_dotenv
from PIL import Image

# Load environment variables
load_dotenv('.env')

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip()
OLLAMA_KEY = os.getenv('OLLAMA', '').strip()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()

# Create a tiny 32x32 red test image
def create_test_image_b64():
    img = Image.new('RGB', (32, 32), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')

TEST_IMAGE_B64 = create_test_image_b64()


def check_groq():
    print("\n" + "=" * 70)
    print("PROBING GROQ MODELS (api.groq.com)")
    print("=" * 70)

    if not GROQ_API_KEY:
        print("[!] No GROQ_API_KEY found in .env")
        return []

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # 1. Fetch model list
    try:
        r = httpx.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"[!] Failed to list Groq models: {r.status_code} - {r.text}")
            return []
        data = r.json().get("data", [])
        all_models = [m["id"] for m in data if m.get("active", True)]
        # Filter out whisper audio models from chat/vision testing
        chat_models = [m for m in all_models if not m.startswith("whisper")]
        print(f"[*] Found {len(chat_models)} active chat/completion models on Groq.")
    except Exception as e:
        print(f"[!] Groq connection error: {e}")
        return []

    results = []

    for model_id in chat_models:
        print(f"\n--> Testing Groq: {model_id} ...", end=" ", flush=True)

        # Step A: Test basic text generation (checks free tier & access)
        text_payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with 'OK'."}],
            "max_tokens": 5
        }
        is_free_and_working = False
        text_error = ""
        try:
            r = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=text_payload,
                timeout=12
            )
            if r.status_code == 200:
                is_free_and_working = True
                print("Text: [FREE/OK]", end=" ", flush=True)
            else:
                err_data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                text_error = err_data.get("error", {}).get("message", r.text[:80])
                print(f"Text: [FAILED - {r.status_code}: {text_error[:40]}]", end=" ", flush=True)
        except Exception as e:
            text_error = str(e)
            print(f"Text: [TIMEOUT/ERR]", end=" ", flush=True)

        # Step B: If text works, test Vision / Image support
        has_vision = False
        vision_note = "N/A"
        if is_free_and_working:
            vision_payload = {
                "model": model_id,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What color is this image? One word."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{TEST_IMAGE_B64}"}}
                    ]
                }],
                "max_tokens": 10
            }
            try:
                rv = httpx.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=vision_payload,
                    timeout=15
                )
                if rv.status_code == 200:
                    has_vision = True
                    resp_txt = rv.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    vision_note = f"YES (Saw color: {resp_txt})"
                    print("-> Vision: [SUPPORTED!]")
                else:
                    err_msg = rv.text[:60].replace("\n", " ")
                    vision_note = f"NO ({err_msg})"
                    print("-> Vision: [No image support]")
            except Exception as e:
                vision_note = f"NO (Error: {str(e)[:40]})"
                print("-> Vision: [Error]")
        else:
            print("")

        results.append({
            "provider": "Groq",
            "model": model_id,
            "free_working": is_free_and_working,
            "vision_supported": has_vision,
            "vision_details": vision_note,
            "error": text_error if not is_free_and_working else ""
        })

    return results


def check_ollama():
    print("\n" + "=" * 70)
    print("PROBING OLLAMA CLOUD (ollama.com)")
    print("=" * 70)

    if not OLLAMA_KEY:
        print("[!] No OLLAMA key found in .env")
        return []

    headers = {
        "Authorization": f"Bearer {OLLAMA_KEY}",
        "Content-Type": "application/json"
    }

    # 1. Fetch available tags/models
    try:
        r = httpx.get("https://ollama.com/api/tags", headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"[!] Failed to list Ollama models: {r.status_code} - {r.text}")
            return []
        data = r.json().get("models", [])
        all_models = [m.get("name") for m in data if m.get("name")]
        print(f"[*] Found {len(all_models)} listed models in Ollama Cloud account.")
    except Exception as e:
        print(f"[!] Ollama connection error: {e}")
        return []

    # Also test standard popular gemma/vision models mentioned in prompt & error hints
    candidates = list(dict.fromkeys(all_models + [
        "gemma4:31b-cloud",
        "gemma2:latest",
        "gemma:latest",
        "llava:latest",
        "llava-phi3:latest",
        "minicpm-v:latest",
        "moondream:latest"
    ]))

    results = []

    for model_id in candidates:
        print(f"\n--> Testing Ollama Cloud: {model_id} ...", end=" ", flush=True)

        # Step A: Test basic text generation (checks free inclusion vs 402 payment required)
        text_payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with 'OK'."}],
            "stream": False
        }
        is_free_and_working = False
        text_error = ""

        try:
            r = httpx.post(
                "https://ollama.com/api/chat",
                headers=headers,
                json=text_payload,
                timeout=15
            )
            if r.status_code == 200:
                is_free_and_working = True
                print("Text: [FREE/OK]", end=" ", flush=True)
            elif r.status_code == 402:
                text_error = "402 Payment Required (Not in free usage tier)"
                print(f"Text: [PAID ONLY - 402]", end=" ", flush=True)
            else:
                try:
                    err_json = r.json()
                    text_error = err_json.get("error", r.text[:60])
                except Exception:
                    text_error = r.text[:60]
                print(f"Text: [FAILED - {r.status_code}: {text_error[:35]}]", end=" ", flush=True)
        except Exception as e:
            text_error = str(e)
            print(f"Text: [TIMEOUT/ERR]", end=" ", flush=True)

        # Step B: If free/working, test Vision / Image support via images: [b64]
        has_vision = False
        vision_note = "N/A"
        if is_free_and_working:
            vision_payload = {
                "model": model_id,
                "messages": [{
                    "role": "user",
                    "content": "What color is this image? Answer in one word.",
                    "images": [TEST_IMAGE_B64]
                }],
                "stream": False
            }
            try:
                rv = httpx.post(
                    "https://ollama.com/api/chat",
                    headers=headers,
                    json=vision_payload,
                    timeout=20
                )
                if rv.status_code == 200:
                    has_vision = True
                    resp_txt = rv.json().get("message", {}).get("content", "").strip()
                    vision_note = f"YES (Saw color: {resp_txt})"
                    print("-> Vision: [SUPPORTED!]")
                else:
                    err_msg = rv.text[:60].replace("\n", " ")
                    vision_note = f"NO ({err_msg})"
                    print("-> Vision: [No image support]")
            except Exception as e:
                vision_note = f"NO (Error: {str(e)[:40]})"
                print("-> Vision: [Error]")
        else:
            print("")

        results.append({
            "provider": "Ollama Cloud",
            "model": model_id,
            "free_working": is_free_and_working,
            "vision_supported": has_vision,
            "vision_details": vision_note,
            "error": text_error if not is_free_and_working else ""
        })

    return results


def print_summary_table(groq_results, ollama_results):
    print("\n" + "=" * 90)
    print("FINAL SUMMARY REPORT: FREE MODELS & VISION SUPPORT")
    print("=" * 90)
    header = f"{'Provider':<14} | {'Model Name':<34} | {'Free/Active':<12} | {'Vision Support':<22}"
    print(header)
    print("-" * 90)

    all_res = groq_results + ollama_results
    free_vision_models = []
    free_text_models = []

    for r in all_res:
        free_str = "YES (Free)" if r["free_working"] else "NO (Paid/Err)"
        vis_str = r["vision_details"]
        if len(vis_str) > 22:
            vis_str = vis_str[:19] + "..."
        print(f"{r['provider']:<14} | {r['model']:<34} | {free_str:<12} | {vis_str:<22}")

        if r["free_working"] and r["vision_supported"]:
            free_vision_models.append((r["provider"], r["model"]))
        elif r["free_working"]:
            free_text_models.append((r["provider"], r["model"]))

    print("=" * 90)
    print("\n🎯 KEY TAKEAWAYS FOR YOUR EMERGENCY PIPELINE:")
    print(f"1. Free Vision-Capable Models ({len(free_vision_models)} found):")
    if free_vision_models:
        for p, m in free_vision_models:
            print(f"   [+] [{p}] {m}")
    else:
        print("   [!] No vision-enabled models passed on the current free quota.")

    print(f"\n2. Free Text-Only Reasoning Models ({len(free_text_models)} found):")
    for p, m in free_text_models:
        print(f"   [+] [{p}] {m}")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    groq_res = check_groq()
    ollama_res = check_ollama()
    print_summary_table(groq_res, ollama_res)
