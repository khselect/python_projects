# market_portfolio

실적 반응 시뮬레이터 · 매크로 국면 대시보드 — **market.sielain.com** (S0 비공개 운영)

- 기획: [PLAN.md](PLAN.md) · Claude Code 맥락: [CLAUDE.md](CLAUDE.md)
- 운영 구성·배포 기록: `khselect/sielain.com`의 `docs/market-subdomain-deploy.md`, `log.md`

```
맥북·휴대폰 브라우저 → Cloudflare Access(이메일 일회용 코드) → sielain-tunnel → market_frontend:8501 (맥미니)
```

## 운영 방식 (parts.sielain.com과 동일)

- 운영 컨테이너는 **`/Users/sielain/docker`(sielain.com 저장소) compose의 `market-app` 서비스**로 띄운다.
- `/docker/market-app`은 맥미니의 이 폴더를 가리키는 symlink다.
- 이 폴더의 `docker-compose.yml`은 **로컬 개발 전용**이다 (`market_dev`, 8503, 터널 미연결).

## 1. 맥미니 최초 설정 (1회)

`<python_projects 클론 경로>`는 맥미니에서 이 저장소를 클론한 위치로 바꿔 읽습니다.

```bash
cd ~/docker && ln -s <python_projects 클론 경로>/market_portfolio market-app
```

```bash
cp ~/docker/market-app/.env.example ~/docker/market-app/.env
```

```bash
cd ~/docker && docker compose up -d --build market-app
```

```bash
curl -s http://127.0.0.1:8502/_stcore/health
```

`ok`가 나오면 Cloudflare 라우트를 추가합니다 (Access 애플리케이션은 2026-11-26 생성 완료):
Zero Trust → Networks → Tunnels → `sielain-tunnel` → **Published application routes** → Subdomain `market` / HTTP / `market_frontend:8501`.
맥북 시크릿 창에서 https://market.sielain.com → Cloudflare 로그인 화면이 뜨면 정상입니다.

## 2. 실적 반응 계산 (④ 종목 상세)

`market-app/.env`에서 `PF_OFFLINE=0`으로 바꾸면 실데이터(yfinance, S0 개인 분석용)로 계산합니다. 바꾼 뒤 컨테이너를 다시 만듭니다.

```bash
cd ~/docker && docker compose up -d market-app
```

```bash
docker compose exec market-app python -m pf.jobs.run publish --group semis
```

```bash
docker compose exec market-app python -m pf.jobs.run show AVGO
```

실적 발표 **전에** 예측을 기록합니다 (같은 실적·기준일 기록은 덮어쓰지 않음):

```bash
docker compose exec market-app python -m pf.jobs.run record AVGO
```

결과는 `market-app/data/publish/ticker/*.json`, 기록은 `market-app/data/predictions/`에 남습니다. 화면은 JSON만 읽으므로 계산 후 새로고침하면 반영됩니다.

## 3. 업데이트

- **어디서든 push만 하면 된다.** 맥미니의 auto-deploy(launchd 5분)가 이 저장소의 upstream을 받아 `market_portfolio/`가 바뀐 경우에만 재빌드한다 (sielain.com `scripts/auto-deploy.sh`).
- 바로 반영: 맥미니에서

```bash
cd <python_projects 클론 경로> && git pull && cd ~/docker && docker compose up -d --build market-app
```

- `config/*.yaml`만 바꾼 경우는 볼륨 연결이라 재빌드 없이 `docker compose restart market-app`.

## 4. 로컬 개발

```bash
pip install -r requirements-dev.txt
```

```bash
pytest -q
```

```bash
PYTHONPATH=src streamlit run app/main.py
```

`PF_OFFLINE=1`(기본)이면 합성 데이터로 동작해 네트워크·API 키가 필요 없습니다. 컨테이너로 확인하려면 이 폴더에서 `docker compose up -d --build` → http://127.0.0.1:8503.

## 5. 지켜야 할 것

- 외부로 가는 경로는 터널 하나뿐. 8502·8503·11434 포트를 공유기에서 열지 않는다.
- `.env`(API 키)는 커밋하지 않는다.
- 맥미니 클론에 미커밋 변경을 남기지 않는다 — auto-deploy가 건너뛴다.
- 공개(S1) 전환은 PLAN.md §9.2 체크리스트를 모두 통과한 뒤, Access 정책 변경이 마지막 단계.
