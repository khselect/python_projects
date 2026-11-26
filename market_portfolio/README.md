# market_portfolio

실적 반응 시뮬레이터 · 매크로 국면 대시보드 — **market.sielain.com** (S0 비공개 운영)

- 기획: [PLAN.md](PLAN.md) · Claude Code 맥락: [CLAUDE.md](CLAUDE.md)
- 구성: Streamlit 1개 컨테이너(`market_frontend`) + 기존 Cloudflare Tunnel(`sielain_tunnel`) + Cloudflare Access

```
맥북·휴대폰 브라우저 → Cloudflare Access(이메일 일회용 코드) → sielain-tunnel → market_frontend:8501 (맥미니)
```

## 1. 맥미니에서 처음 배포

아래 `~/python_projects`는 맥미니에서 이 저장소를 클론한 위치로 바꿔 읽습니다 (air 대시보드와 같은 클론).

```bash
cd ~/python_projects && git fetch origin && git checkout claude/amazing-newton-hvyffo && git pull
```

```bash
cd market_portfolio && cp .env.example .env
```

```bash
docker compose up -d --build
```

확인 (맥미니 로컬, Cloudflare를 거치지 않음):

```bash
curl -s http://127.0.0.1:8502/_stcore/health
```

`ok`가 나오면 브라우저에서 http://127.0.0.1:8502 로 화면 5개를 확인합니다.

> `network docker_sielain_net not found` 오류가 나면 `/Users/sielain/docker` 스택(터널)이 꺼져 있는 것입니다. 그 스택을 먼저 올립니다.

## 2. Cloudflare 설정 (순서 중요)

1. **Access 애플리케이션** — 완료 (2026-11-26). `market.sielain.com`, 정책 `owner-only`(Allow, 본인 이메일), 로그인 One-time PIN.
2. **터널 라우트 추가** — 1번이 저장된 뒤에만:
   Zero Trust → Networks → Tunnels → `sielain-tunnel` → **Published application routes** → Add
   - Subdomain `market`, Domain `sielain.com`
   - Type `HTTP`, URL `market_frontend:8501`
   - "Hostname routes (Beta)" 탭은 WARP 전용이므로 쓰지 않음
3. **확인** — 맥북 시크릿 창에서 https://market.sielain.com
   - Cloudflare 로그인 화면이 뜨면 정상 → 이메일 입력 → 메일로 온 코드 입력 → 앱 화면
   - 로그인 없이 앱이 바로 보이면 Access가 적용되지 않은 것 → 라우트를 지우고 Access 설정 확인
4. (권장) 검색 노출 방지: Rules → Transform Rules → Response Header 수정, `market.sielain.com`에 `X-Robots-Tag: noindex` 추가

## 3. 업데이트

```bash
cd ~/python_projects && git pull && cd market_portfolio && docker compose up -d --build
```

`config/*.yaml`만 바꾼 경우에는 볼륨으로 연결돼 있어 재빌드 없이 `docker compose restart app`이면 됩니다.

## 4. 노트북·로컬 개발

```bash
pip install -r requirements-dev.txt
```

```bash
pytest -q
```

```bash
PYTHONPATH=src streamlit run app/main.py
```

`PF_OFFLINE=1`(기본)이면 합성 데이터로 동작해 네트워크·API 키가 필요 없습니다.

## 5. 지켜야 할 것

- 외부로 가는 경로는 터널 하나뿐. 8502·11434 포트를 공유기에서 열지 않는다 (compose도 127.0.0.1에만 바인딩).
- `.env`(API 키)는 커밋하지 않는다.
- 공개(S1) 전환은 PLAN.md §9.2 체크리스트를 모두 통과한 뒤, Access 정책 변경이 마지막 단계.
