# xrp_regime_forecast.py
# -----------------------------------------------------------------------------
# XRP(리플) 일간 시세로 횡보/상승 레짐을 식별하고,
# 횡보 길이 분포 -> 위험률(hazard) -> k일 내 상승 전환확률을 추정.
# - 데이터 로딩 안정화: yfinance 실패/빈 DF/MultiIndex 발생 시 Binance Klines로 자동 폴백
# - 모든 지표 Series 1차원 보장
# -----------------------------------------------------------------------------

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
import warnings
warnings.filterwarnings("ignore")

# =========================== (A) 유틸: 데이터 소스 ============================

def _flatten_yf_columns(df, ticker):
    """yfinance가 MultiIndex로 반환되는 경우를 평탄화"""
    if isinstance(df.columns, pd.MultiIndex):
        # 티커 레벨이 존재할 경우 해당 티커 서브프레임을 선택
        top = [lvl for lvl in df.columns.levels[0]]
        if ticker in top:
            df = df.xs(ticker, axis=1, level=0, drop_level=True)
        else:
            # 단일 티커라면 첫 레벨만 제거
            df.columns = df.columns.get_level_values(-1)
    return df

def _normalize_ohlcv_cols(df):
    """Open/High/Low/Close/Volume 컬럼을 소문자 표준명으로 정규화"""
    rename_map = {}
    for c in df.columns:
        lc = c.lower().strip()
        if lc in ["open", "high", "low", "close", "volume", "adj close", "adj_close"]:
            rename_map[c] = lc.replace(" ", "_")
    df = df.rename(columns=rename_map)
    # 표준 세트 만들기
    need = {"open", "high", "low", "close", "volume"}
    have = set(df.columns)
    # 일부가 부족하면 실패로 간주 (지표 계산 정확도 보호)
    if not need.issubset(have):
        return None
    return df[list(need)].copy().sort_index()

def _download_yfinance(ticker="XRP-USD", start="2015-01-01", end=None):
    import yfinance as yf
    end = end or datetime.today().strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    df = _flatten_yf_columns(df, ticker)
    norm = _normalize_ohlcv_cols(df)
    return norm

def _download_binance_klines(symbol="XRPUSDT", interval="1d", start=None, end=None, limit=1000):
    """Binance 공개 API에서 일봉 OHLCV 다운로드 (UTC 기준)."""
    import requests
    base = "https://api.binance.com/api/v3/klines"

    # 날짜 → ms
    def to_ms(d):
        if d is None:
            return None
        if isinstance(d, str):
            d = pd.to_datetime(d)
        if isinstance(d, datetime) and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return int(d.timestamp() * 1000)

    start_ms = to_ms(start) if start else None
    end_ms = to_ms(end) if end else None

    rows = []
    cur = start_ms
    while True:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if cur is not None:
            params["startTime"] = cur
        if end_ms is not None:
            params["endTime"] = end_ms

        r = requests.get(base, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        rows.extend(data)
        # 다음 구간으로 이동
        last_close = data[-1][6]  # closeTime (ms)
        next_start = last_close + 1
        if end_ms is not None and next_start > end_ms:
            break
        # Binance는 최대 1000개씩 반환 → 계속 루프
        if len(data) < limit:
            break
        cur = next_start

    if not rows:
        return None

    cols = [
        "open_time","open","high","low","close","volume","close_time",
        "quote_asset_volume","num_trades","taker_buy_base","taker_buy_quote","ignore"
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").tz_convert(None)  # naive 로 변환
    df = df[["open","high","low","close","volume"]].sort_index()
    return df

def load_xrp(start="2015-01-01", end=None, ticker="XRP-USD"):
    """
    우선 yfinance로 시도 → 실패/결측 시 Binance Klines(XRPUSDT)로 폴백.
    반환: 표준 OHLCV DataFrame(index=Datetime, cols=open,high,low,close,volume)
    """
    # 1) yfinance
    df = None
    try:
        df = _download_yfinance(ticker=ticker, start=start, end=end)
        if df is not None and not df.empty:
            print("[INFO] Data source: yfinance")
            return df.dropna()
    except Exception as e:
        print(f"[WARN] yfinance download failed: {e}")

    # 2) Binance Klines (Binance 상장(2017~) 데이터)
    try:
        # Binance는 2017년 이후 지원 → 시작일이 너무 이르면 보수적으로 2017-01-01로 올림
        start_dt = pd.to_datetime(start) if start else pd.Timestamp("2017-01-01")
        if start_dt < pd.Timestamp("2017-01-01"):
            start_dt = pd.Timestamp("2017-01-01")
        end_dt = pd.to_datetime(end) if end else None

        dfb = _download_binance_klines(
            symbol="XRPUSDT",
            interval="1d",
            start=start_dt,
            end=end_dt,
            limit=1000
        )
        if dfb is not None and not dfb.empty:
            print("[INFO] Data source: Binance Klines")
            return dfb.dropna()
    except Exception as e:
        print(f"[WARN] Binance download failed: {e}")

    raise RuntimeError("시세 데이터를 가져오지 못했습니다. 네트워크/방화벽/티커 설정을 확인하세요.")

# ========================= (B) 지표/레짐 함수들 ===============================

def compute_dmi_adx(df: pd.DataFrame, n: int = 14):
    high, low, close = df["high"], df["low"], df["close"]

    up = high.diff()
    down = -low.diff()

    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / n, adjust=False).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()

    return plus_di.astype(float), minus_di.astype(float), adx.astype(float), atr.astype(float)

def bollinger_bandwidth(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std()
    upper = ma + k * sd
    lower = ma - k * sd
    return ((upper - lower) / ma.replace(0, np.nan)).astype(float)

def choppiness_index(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    sum_tr = tr.rolling(n).sum()
    highest = high.rolling(n).max()
    lowest = low.rolling(n).min()

    denom = (highest - lowest).replace(0, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        chop = 100 * np.log10(sum_tr / denom) / np.log10(n)
    return chop.astype(float)

def ema_slope(close: pd.Series, n: int = 50):
    ema = close.ewm(span=n, adjust=False).mean()
    slope = ema.diff()
    return ema.astype(float), slope.astype(float)

def label_regimes_rule(df: pd.DataFrame) -> pd.DataFrame:
    plus_di, minus_di, adx, atr = compute_dmi_adx(df, n=14)
    bbw = bollinger_bandwidth(df["close"], n=20, k=2.0)
    chop = choppiness_index(df, n=14)
    ema50, ema50_slope = ema_slope(df["close"], n=50)

    out = df.copy()
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di
    out["adx"] = adx
    out["bbw"] = bbw
    out["chop"] = chop
    out["ema50"] = ema50
    out["ema50_slope"] = ema50_slope

    bbw_q20 = out["bbw"].quantile(0.20)

    cond_up = (out["adx"] >= 25) & (out["plus_di"] > out["minus_di"]) & (out["ema50_slope"] > 0)
    cond_range = (out["adx"] <= 18) | (out["chop"] >= 61.8) | (out["bbw"] <= bbw_q20)

    out["label_rule"] = "other"
    out.loc[cond_range, "label_rule"] = "range"
    out.loc[cond_up, "label_rule"] = "up"
    return out

def label_regimes_hmm(df: pd.DataFrame):
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        return None

    X = pd.DataFrame(index=df.index)
    X["ret"] = np.log(df["close"]).diff()
    X["vol20"] = X["ret"].rolling(20).std()
    _, _, adx, _ = compute_dmi_adx(df, n=14)
    X["adx"] = (adx / 100.0)
    X = X.dropna()

    hmm = GaussianHMM(n_components=3, covariance_type="full", n_iter=500, random_state=42)
    hmm.fit(X.values)
    states = hmm.predict(X.values)

    X["state"] = states.astype(int)
    state_means = X.groupby("state")["ret"].mean().sort_values()
    mapping = {state_means.index[0]:"down", state_means.index[1]:"range", state_means.index[2]:"up"}

    labels = X["state"].map(mapping)

    out = pd.DataFrame(index=df.index)
    out["label_hmm"] = np.nan
    out.loc[X.index, "label_hmm"] = labels
    return out, hmm, X

def episode_lengths(labels: np.ndarray, target: str) -> np.ndarray:
    run_lengths, current = [], 0
    for v in labels:
        if v == target:
            current += 1
        else:
            if current > 0:
                run_lengths.append(current)
                current = 0
    if current > 0:
        run_lengths.append(current)
    return np.array(run_lengths, dtype=float)

def empirical_hazard(lengths: np.ndarray) -> dict:
    hazard = {}
    if lengths is None or len(lengths) == 0:
        return hazard
    maxd = int(np.nanmax(lengths))
    for d in range(1, maxd + 1):
        num = float(np.sum(lengths == d))
        den = float(np.sum(lengths >= d))
        hazard[d] = (num / den) if den > 0 else 0.0
    return hazard

def prob_switch_within_k(hazard: dict, current_run_len: int, k: int) -> float:
    if not hazard:
        return 0.0
    max_key = max(hazard.keys())
    p_survive = 1.0
    for j in range(current_run_len, current_run_len + k):
        hj = float(hazard.get(j, hazard[max_key]))
        p_survive *= max(0.0, 1.0 - hj)
    return float(1.0 - p_survive)

# ---------------------- 백테스트 ----------------------
def backtest_regime(df, label_col="label_final", init_cash=10000.0):
    """
    진입: 레짐이 'up'으로 전환되는 날 종가 매수
    청산: 레짐이 'up'이 아닌 날(= range/down)로 전환되는 날 종가 매도
    """
    # 안전장치: 라벨 결측 제거
    df = df.copy()
    if label_col not in df.columns:
        raise ValueError(f"{label_col} 컬럼이 없습니다.")
    if "close" not in df.columns:
        raise ValueError("close 컬럼이 없습니다.")

    n = len(df)
    if n == 0:
        raise ValueError("데이터가 비었습니다.")

    cash = float(init_cash)
    position = 0.0
    entry_price = np.nan

    # 첫 날의 자산가치(현금)로 시작 → 길이 맞추기용
    equity_curve = [cash]

    trades = []

    # i=1부터 마지막 날까지 순회
    for i in range(1, n):
        today_label = df[label_col].iloc[i]
        yesterday_label = df[label_col].iloc[i-1]
        price = float(df["close"].iloc[i])

        # 매수: 어제 up 아님 & 오늘 up, 현재 무포지션
        if (yesterday_label != "up") and (today_label == "up") and (position == 0.0):
            position = cash / price
            entry_price = price
            cash = 0.0
            trades.append({"date": df.index[i], "action": "BUY", "price": price})

        # 매도: 어제 up & 오늘 up 아님, 현재 보유 중
        elif (yesterday_label == "up") and (today_label != "up") and (position > 0.0):
            cash = position * price
            position = 0.0
            trades.append({"date": df.index[i], "action": "SELL", "price": price})

        # 오늘 자산가치 기록 (현금 + 보유수량*가격)
        equity = cash + position * price
        equity_curve.append(equity)

    # 길이 확인 및 할당 (== len(df))
    if len(equity_curve) != n:
        # 혹시라도 불일치가 있으면, 앞에서부터 자르거나 NaN으로 보정
        equity_curve = equity_curve[:n]

    df["equity"] = equity_curve

    # 성과 지표
    total_return = df["equity"].iloc[-1] / init_cash - 1.0
    years = (df.index[-1] - df.index[0]).days / 365.25 if n > 1 else 0.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    running_max = df["equity"].cummax()
    drawdown = df["equity"] / running_max - 1.0
    mdd = float(drawdown.min())

    stats = {
        "총 수익률": float(total_return),
        "연평균수익률(CAGR)": float(cagr),
        "최대낙폭(MDD)": mdd,
        "거래횟수": len(trades),
    }
    return df, trades, stats

# ---------------------- 시각화 ----------------------
def plot_regime_with_probs(df, probs_dict):
    plt.figure(figsize=(14,8))

    # 가격 + 레짐 색칠
    colors = {"up":"green", "range":"gray", "down":"red", "other":"lightblue"}
    for regime, group in df.groupby("label_final"):
        plt.plot(group.index, group["close"], color=colors.get(regime,"black"), label=regime)

    plt.title("XRP Price with Regimes")
    plt.legend()
    plt.show()

    # 전환확률 시각화
    plt.figure(figsize=(10,4))
    for k,v in probs_dict.items():
        plt.bar(str(k)+"일 내", v, color="skyblue")
    plt.title("횡보 → 상승 전환 확률")
    plt.ylabel("확률")
    plt.show()

# ============================== (C) 메인 실행 =================================

if __name__ == "__main__":
    df = load_xrp(start="2016-01-01")
    df_rule = label_regimes_rule(df)

    # 1) 기본 레이블은 규칙 기반으로 설정
    df_rule["label_final"] = df_rule["label_rule"].copy()

    # 2) HMM 시도 후 성공 시에만 합치고, label_final을 HMM으로 보강
    hmm_pack = label_regimes_hmm(df)
    if hmm_pack is not None:
        df_hmm, hmm, Xh = hmm_pack
        # 왼쪽 조인 (인덱스 기준); HMM 결과가 일부 날짜에만 있을 수 있음
        df_rule = df_rule.join(df_hmm, how="left")

        # HMM 라벨이 생긴 경우에만 덮어쓰기
        if "label_hmm" in df_rule.columns:
            df_rule["label_final"] = df_rule["label_hmm"].fillna(df_rule["label_final"])
    else:
        hmm, Xh = None, None
        # HMM이 없으면 label_hmm 컬럼을 만들어두면 이후 코드에서 안전
        df_rule["label_hmm"] = np.nan

    # ---------------- 백테스트 ----------------
    df_bt, trades, stats = backtest_regime(df_rule, label_col="label_final")
    print("백테스트 성과지표:", stats)

    # ---------------- 전환확률 ----------------
    lbl = df_rule["label_final"].dropna()
    lengths_range = episode_lengths(lbl.values, "range")
    haz_range = empirical_hazard(lengths_range)
    # 현재 레짐이 range가 아닌 경우 기본 길이를 1로 두는 예시
    last_label = lbl.iloc[-1]
    last_run_len = 1
    for v in lbl.iloc[:-1][::-1]:
        if v == last_label:
            last_run_len += 1
        else:
            break
    base_len = last_run_len if last_label == "range" else 1

    k_list = [5, 10, 20]
    probs = {k: prob_switch_within_k(haz_range, base_len, k) for k in k_list}
    print("전환확률:", {k: round(v, 4) for k, v in probs.items()})

    # ---------------- 시각화 ----------------
    plot_regime_with_probs(df_bt, probs)

    # (선택) HMM 보조지표 출력
    if hmm is not None and Xh is not None and len(Xh) > 0:
        trans = hmm.transmat_
        st_means = Xh.groupby("state")["ret"].mean().sort_values()
        s_down, s_range, s_up = st_means.index.tolist()
        p_rr = float(trans[s_range, s_range])
        expected_range_duration = 1.0 / (1.0 - p_rr) if (1.0 - p_rr) > 0 else np.inf
        k = 10
        Ak = np.linalg.matrix_power(trans, k)
        current_state = int(Xh["state"].iloc[-1])
        prob_to_up_in_k = float(Ak[s_up, current_state])
        print("────────────────────────────────────────────────────────")
        print("[HMM 보조지표]")
        print(f"전이행렬(range->range)={p_rr:.3f}  → 기대 횡보 체류기간≈ {expected_range_duration:.2f} 영업일")
        print(f"HMM 기준 {k}일 내 '상승 상태' 도달확률: {prob_to_up_in_k:.3f}")