import requests
import json

url = "http://127.0.0.1:11434/api/embeddings"
payload = {
    "model": "nomic-embed-text",
    "prompt": "Hello world"
}

try:
    response = requests.post(url, json=payload)
    print(f"상태 코드: {response.status_code}")
    if response.status_code == 200:
        print("✅ 성공! Ollama와 연결되었습니다.")
    else:
        print(f"❌ 실패: {response.text}")
except Exception as e:
    print(f"❌ 치명적 오류: {e}")