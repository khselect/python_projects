# market_portfolio — Claude Code 맥락

실적 반응 시뮬레이터 + 매크로 국면 대시보드. 게시: market.sielain.com (S0: Cloudflare Access 뒤, 본인만).
기준 문서는 `PLAN.md` 하나. **필요한 절만 지정해서 읽는다** (예: "PLAN.md §7.5만").

## 원칙 (PLAN.md §2, §12 요약)
- 숫자·통계·시뮬레이션은 전부 코드. LLM은 숫자를 만들지 않는다.
- 페이지 조회당 LLM 호출 0. 화면은 사전 계산 JSON을 읽기만 한다.
- 유료 API 호출 0. AI 해설은 로컬 Ollama(gemma3)만.
- 문구는 서술형("과거 강세 우위"). "사라·팔라·늘려라·줄여라·헤지하라", "반드시·확실히·보장" 금지.
- 모든 확률 옆에 표본 수·기간·기준일. 손실 쪽 숫자(90% 하단, CVaR)를 기대값과 같은 크기로.
- 개인정보(이름·이메일·아이디·비밀번호) 받지 않음.

## 구조
- `src/pf/` 패키지 (PYTHONPATH=src). 설정은 `pf.settings`, YAML 로드·검증은 `pf.config`.
- `app/main.py` Streamlit 진입점(`st.navigation`), 화면은 `app/views/`, 공통은 `app/common.py`.
- `config/coverage.yaml` 50종목(10그룹×5) + 테마. 테마 종목은 반드시 50종목 안.
- `config/glossary.yaml` ⓘ 가이드 단일 출처. `config/model.yaml` 시뮬·보정 관문 기본값.
- `data/` 는 커밋 안 함 (Parquet·SQLite·게시 JSON).

## 개발
```
pip install -r requirements-dev.txt
pytest -q
PYTHONPATH=src streamlit run app/main.py      # PF_OFFLINE=1(기본) → 합성 데이터
```
- 모듈 하나씩 작성·테스트. 전체 재생성 금지. 데이터 파일을 직접 읽히지 말고 digest만.
- `PF_OFFLINE=1`에서 네트워크 없이 모든 화면이 떠야 한다.

## 배포 (맥미니)
- `git pull && docker compose up -d --build` → 컨테이너 `market_frontend`, 네트워크 `docker_sielain_net`.
- 터널은 원격 관리형(토큰): 라우트는 Cloudflare 대시보드 Published application routes에서만.
- 호스트 포트 127.0.0.1:8502 (air가 8501 사용). Ollama는 macOS 직접 설치, `host.docker.internal:11434`.

## MVP 순서 (PLAN.md §13)
골격 → ④ 종목 반응 분포(AVGO, 12/09 실적 전) → ① 매크로 국면 → ②③ 그룹.
