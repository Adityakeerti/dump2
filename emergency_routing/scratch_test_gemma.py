import os, httpx, json
from dotenv import load_dotenv

load_dotenv('.env')

ollama_key = os.getenv('OLLAMA', '').strip()
groq_key = os.getenv('GROQ_API_KEY', '').strip()

print("Testing Ollama Cloud gemma4:31b-cloud...")
try:
    url = "https://ollama.com/api/chat"
    payload = {
        "model": "gemma4:31b-cloud",
        "messages": [{"role": "user", "content": "You are an emergency triage AI. Respond in JSON with format: {\"dispatch\": \"AMBULANCE\", \"reason\": \"severe accident detected\"}"}],
        "stream": False,
        "format": "json"
    }
    r = httpx.post(url, headers={"Authorization": f"Bearer {ollama_key}"}, json=payload, timeout=20)
    print("Ollama gemma4:31b-cloud status:", r.status_code)
    if r.status_code == 200:
        print("Ollama response content:", r.json().get("message", {}).get("content"))
    else:
        print("Ollama err:", r.text)
except Exception as e:
    print("Ollama exception:", e)
