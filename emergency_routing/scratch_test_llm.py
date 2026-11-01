import os, httpx, json
from dotenv import load_dotenv

load_dotenv('.env')

gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
groq_key = os.getenv('GROQ_API_KEY', '').strip()
ollama_key = os.getenv('OLLAMA', '').strip()

print("1. Testing Gemini 3.8 Flash...")
try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={gemini_key}"
    payload = {
        "contents": [{"parts": [{"text": "You are an emergency triage system. Output JSON format: {\"dispatch\": \"AMBULANCE\", \"confidence\": 0.95}"}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    r = httpx.post(url, json=payload, timeout=10)
    print("Gemini response code:", r.status_code)
    if r.status_code == 200:
        print("Gemini response:", r.json()["candidates"][0]["content"]["parts"][0]["text"])
    else:
        print("Gemini err:", r.text[:200])
except Exception as e:
    print("Gemini exception:", e)

print("\n2. Testing Ollama Cloud chat...")
try:
    # Test ollama cloud chat endpoint with one of the available models, e.g. glm-5.3-flash or deepseek-v4.1-flash
    url = "https://ollama.com/api/chat"
    payload = {
        "model": "deepseek-v4.1-flash",
        "messages": [{"role": "user", "content": "You are an emergency triage AI. Output JSON format: {\"dispatch\": \"POLICE\", \"confidence\": 0.9}"}],
        "stream": False,
        "format": "json"
    }
    r = httpx.post(url, headers={"Authorization": f"Bearer {ollama_key}"}, json=payload, timeout=15)
    print("Ollama chat response code:", r.status_code)
    if r.status_code == 200:
        print("Ollama response:", r.json().get("message", {}).get("content"))
    else:
        print("Ollama err:", r.text[:200])
except Exception as e:
    print("Ollama exception:", e)
