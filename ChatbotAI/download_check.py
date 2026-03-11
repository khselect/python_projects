import os

# [핵심] 데드락 방지를 위한 환경변수 설정 (반드시 import 전에 설정)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

print("1. 라이브러리 임포트 중... (경고 메시지는 무시하세요)")
from langchain_huggingface import HuggingFaceEmbeddings

print("2. 모델 다운로드 및 로드 시도 (잠시만 기다려주세요)...")

try:
    # 모델 로드 (Mac에서는 CPU로 강제하는 것이 가장 안정적입니다)
    embeddings = HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'}, 
        encode_kwargs={'normalize_embeddings': True}
    )
    print(">> 모델 로드 성공!")

    print("3. 테스트 문장 임베딩...")
    vector = embeddings.embed_query("테스트 문장입니다.")
    print(f"4. 성공! 벡터 길이: {len(vector)}")
    print("✅ 이제 app.py를 실행해도 됩니다!")

except Exception as e:
    print(f"❌ 오류 발생: {e}")