"""F20 AI 해설 (로컬 sLLM). 숫자·판정·거절은 코드, LLM은 문장만 (PLAN.md §8.1).

  digest  : 게시 JSON → 근거 문장 (숫자는 여기서만 나온다)
  client  : Ollama 호출 / 오프라인용 가짜 LLM
  guard   : 답변 검증 (근거에 없는 숫자·날짜, 금지어, 길이) + 범위 밖 질문 거절
  pregen  : 매일 배치에서 미리 생성 → data/publish/ai/*.json (화면은 읽기만)
"""
