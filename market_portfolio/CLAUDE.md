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
- `app/main.py` Streamlit 진입점(`st.navigation`), 화면은 `app/views/`(⓪~④, 기본 화면 ⓪ — 기본 화면의 url_path는 항상 ""), 공통은 `app/common.py`.
- 세로 3분할: 오른쪽 종합 인사이트 패널 `app/panel.py`(항상 표시, sticky). 규칙은 `pf.synth.rules`(F19). 패널은 화면보다 먼저 렌더.
- `config/coverage.yaml` 50종목(10그룹×5) + 테마. 테마 종목은 반드시 50종목 안.
- `config/glossary.yaml` ⓘ 가이드 단일 출처. `config/model.yaml` 시뮬·보정 관문·국면 경계(macro.market). `config/overview.yaml` ⓪ 패널 구성.
- `data/` 는 커밋 안 함 (Parquet·SQLite·게시 JSON).

## 개발
```
pip install -r requirements-dev.txt
pytest -q
PYTHONPATH=src streamlit run app/main.py      # PF_OFFLINE=1(기본) → 합성 데이터
```
- 모듈 하나씩 작성·테스트. 전체 재생성 금지. 데이터 파일을 직접 읽히지 말고 digest만.
- `PF_OFFLINE=1`에서 네트워크 없이 모든 화면이 떠야 한다.

## 문서
- `docs/user-guide.md` 사용 설명서, `docs/interactive-guide.html` 인터랙티브 가이드(단일 파일, 스크린샷 내장)
- 화면을 바꾸면: 스크린샷 다시 찍기(`docs/screenshots/`, 합성 데이터) → `python docs/build_interactive_guide.py`. 가이드의 계산 규칙(국면 점수·5일 확정·종합 판단)은 `pf.macro`·`pf.synth.rules`와 같게 유지

## 배포 (맥미니)
- 운영은 sielain.com 저장소(`/Users/sielain/docker`) compose의 `market-app` 서비스(`market_frontend`, 127.0.0.1:8502). `/docker/market-app` → 이 폴더 symlink.
- push만 하면 맥미니 auto-deploy(5분)가 `market_portfolio/` 변경 시 재빌드. 운영 기록은 sielain.com `log.md`·`docs/market-subdomain-deploy.md`.
- 이 폴더의 docker-compose.yml은 로컬 개발 전용(`market_dev`, 8503).
- 터널은 원격 관리형(토큰): 라우트는 Cloudflare 대시보드 Published application routes에서만. Ollama는 macOS 직접 설치, `host.docker.internal:11434`.

## 배치 명령
```
python -m pf.jobs.run daily                              # 매일 배치: 산업 그룹 10개 + 실적 1~5일 전 예측 기록
python -m pf.jobs.run publish --group semis [--cache]   # 그룹 실적 반응 계산 → data/publish/ticker/*.json
python -m pf.jobs.run show AVGO                          # 게시 결과 요약 (Claude에는 이것만 보여준다)
python -m pf.jobs.run record AVGO                        # 실적 전 예측 기록 → data/predictions/
python -m pf.jobs.run ai [--show semis]                  # AI 해설 미리 생성만 / 1건 확인 (근거·시도·템플릿 사유)
```
- 운영: `docker compose exec market-app python -m pf.jobs.run ...` (`/Users/sielain/docker`에서)
- 매일 07:15 KST `market-jobs` 컨테이너(`pf.jobs.scheduler`)가 `daily` 실행. 결과 `data/publish/status.json`
- 컨테이너 시작 시 오늘 배치가 없거나 `status.json`의 `code_hash`(src/pf + config 해시)가 현재와 다르면 즉시 1회 실행 → 새 기능 배포 직후에도 화면이 바로 채워짐
- 그룹·캘린더: `pf.events.reactions.event_paths`(CAR 경로) → `pf.publish.group`(data/publish/group/*.json, calendar.json). 종목 JSON을 읽으므로 publish_all에서 종목 계산 뒤 실행
- 밸류에이션: `pf.data.fundamentals`(Alpha Vantage 분기 재무, `ALPHAVANTAGE_API_KEY`, 하루 20회 대기열) → `pf.valuation`(TTM·분할 보정·그룹 합산·선행 P/E 누적) → `pf.publish.valuation`(data/publish/valuation/*.json). 실패해도 다른 배치 결과는 유지
- AI 해설(F20 1단계): `pf.ai.digest`(게시 JSON → 근거 문장, 숫자는 여기서만) → `pf.ai.client`(Ollama `/api/chat`, 오프라인은 FakeLLM, `PF_AI_BACKEND=ollama|fake|off`) → `pf.ai.guard`(근거 대조·금지어·길이, 실패 시 1회 재시도) → `pf.ai.pregen`(매일 배치 끝, data/publish/ai/*.json, 실패·Ollama 없음은 템플릿). 확인: `python -m pf.jobs.run ai --show semis`. 프롬프트를 바꾸면 `PROMPT_VERSION`을 올린다
- 매크로(v0.21 두 속도): `pf.data.fred`(FRED, 키 `FRED_API_KEY`) + Yahoo(^VIX·^GSPC·^NDX·섹터 ETF) → `pf.macro.indicators`(매크로 층 6개 5일 확정 + 시장 층 4개 2일 확정, −10~+10, 경계 ±4, 급변 규칙 — 진입 즉시·해제 5거래일 히스테리시스) → `pf.macro.publish`(data/publish/macro.json, 2007년부터 계산) + `pf.macro.evaluate`(같은 계산으로 52주 고점 −15% 하락 구간의 탐지 지연·오경보, 6개 안·v0.21·현재안 비교 → macro_eval.json, `python -m pf.jobs.run macro-eval`). 신용(ICE) 값은 화면에 내지 않는다
- ⓪ 시장 개요: `config/overview.yaml` → `pf.publish.overview`(data/publish/overview.json). market_monitor 패널 4개(지수·원자재·국채·섹터)를 옮긴 것. 수치만, 판정은 ①
- 모델: `pf.events.reactions`(반응일·β 조정 초과수익) → `pf.sim.mixture`(3성분 t 혼합 MAP-EM, 그룹 축소) → `pf.sim.reaction_mc`(40만 회)

## MVP 순서 (PLAN.md §13)
골격 → ④ 종목 반응 분포(AVGO, 12/09 실적 전) → ① 매크로 국면 → ②③ 그룹 — 모두 구현됨(11-26). ⓪ 시장 개요·두 속도 국면 점수(11-27). 다음은 v1(F8·F9·F17·F20 2단계·F21).
