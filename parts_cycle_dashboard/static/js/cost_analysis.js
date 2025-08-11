// cost_analysis.js (UI 업그레이드 v2) — 부품탭 확률표: 최소확률 필터 + CSV + v-scroll 고정
document.addEventListener("DOMContentLoaded", function () {
  ensureEvidenceStyles(); // ⬅️ v-scroll 고정용 CSS 주입
  loadBudgetForecast();
  loadReplacementCostChart();
  loadPriorityMaintenance();
});

let replacementCostChart = null;

/* ---------- 공통 ---------- */
async function fetchData(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
const fmtWon = (v) => (v ?? 0).toLocaleString("ko-KR") + " 원";
const fmtInt = (v) => (v ?? 0).toLocaleString("ko-KR");

/* ---------- 1) 고장 예측 기반 예산 계획 ---------- */
function loadBudgetForecast() {
  const section = document.getElementById("budget-forecast-section");
  fetchData("/api/cost/budget_forecast")
    .then((data) => {
      if (data.error) {
        section.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류 발생: ${data.error}</div>`;
        return;
      }
      const won = (v) => (v ?? 0).toLocaleString("ko-KR") + " 원";
      const n2 = (v) => Number(v ?? 0).toFixed(2);
      const horizonDays =
        data.assumptions && data.assumptions.horizon_days
          ? data.assumptions.horizon_days
          : 90;

      const totalCost = data.total_forecast_cost || 0;
      const ciLow = data.ci95_low ?? null;
      const ciHigh = data.ci95_high ?? null;

      // 부품별 탭 HTML
      const tabsHtml = buildPartTabs(
        data.forecast_details || {},
        data.explain || [],
        horizonDays
      );

      section.innerHTML = `
        <div class="col-md-4 mb-3">
          <div class="card kpi-card h-100">
            <div class="card-body">
              <div class="text-muted">총 예상 교체 비용</div>
              <div class="kpi-value text-primary mt-2">${won(totalCost)}</div>
              <div class="mt-3 small text-muted">
                <div><strong>간이 산식</strong> : Σ(예상 교체 수 × 평균 단가)</div>
                <div><strong>오차 범위(95%)</strong> : ${
                  ciLow !== null ? won(ciLow) : "—"
                } ~ ${ciHigh !== null ? won(ciHigh) : "—"}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="col-md-8 mb-3">
          ${tabsHtml}
        </div>`;
    })
    .catch((error) => {
      console.error("Error loading budget forecast:", error);
      section.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류가 발생했습니다.</div>`;
    });
}

/* 부품 탭 + 확률표(%) + 최소확률 필터 + CSV */
function buildPartTabs(details, explainRows, horizonDaysDefault) {
  const won = (v) => (v ?? 0).toLocaleString("ko-KR") + " 원";
  const n2 = (v) => Number(v ?? 0).toFixed(2);

  // part_id별 explain 그룹
  const explainByPart = {};
  (explainRows || []).forEach((r) => {
    const pid = r.part_id || "";
    if (!pid) return;
    (explainByPart[pid] ||= []).push(r);
  });

  const partIds = Object.keys(details);
  if (partIds.length === 0)
    return '<p class="text-muted mb-0">예상 대상 부품이 없습니다.</p>';

  let nav = `<ul class="nav nav-tabs flex-nowrap overflow-auto" role="tablist">`;
  let panes = `<div class="tab-content border border-top-0 rounded-bottom p-3 bg-white">`;

  partIds.forEach((partId, idx) => {
    const v = details[partId] || {};
    const safe = `part-${partId.replace(/[^a-zA-Z0-9_-]/g, "") || idx}`;
    const active = idx === 0 ? "active" : "";

    nav += `
      <li class="nav-item">
        <button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#${safe}" type="button" role="tab">
          ${partId}
        </button>
      </li>`;

    const rowsAll = (explainByPart[partId] || []).slice(); // 복사

    panes += `
      <div class="tab-pane fade show ${active}" id="${safe}" role="tabpanel">
        <div class="row g-3 align-items-stretch">
          <div class="col-lg-4">
            <div class="card h-100 text-center">
              <div class="card-header fw-semibold">${partId}</div>
              <div class="card-body">
                <div class="small text-muted mb-1">예상 교체 수량</div>
                <div class="fs-4 fw-bold">${n2(v.count)} 개</div>
                <div class="small text-muted mt-3 mb-1">평균 단가(±σ)</div>
                <div class="fs-6">${won(
                  v.unit_cost_mean
                )} <span class="text-muted">± ${won(
      v.unit_cost_std
    )}</span></div>
                <div class="small text-muted mt-3 mb-1">예상 비용</div>
                <div class="fs-5 fw-semibold">${won(v.total_cost)}</div>
              </div>
            </div>
          </div>

          <div class="col-lg-8">
            <div class="d-flex gap-2 justify-content-end align-items-center mb-2">
              <div class="input-group input-group-sm" style="width: 220px;">
                <span class="input-group-text">기간(H)</span>
                <select class="form-select" id="${safe}-horizon">
                  <option value="30">30일</option>
                  <option value="60">60일</option>
                  <option value="90" selected>90일</option>
                  <option value="180">180일</option>
                </select>
              </div>
              <div class="input-group input-group-sm" style="width: 200px;">
                <span class="input-group-text">최소 확률</span>
                <input class="form-control" id="${safe}-minpct" type="number" step="0.1" min="0" max="100" value="1.0">
                <span class="input-group-text">%</span>
              </div>
              <button id="${safe}-csv" class="btn btn-outline-secondary btn-sm">CSV 다운로드</button>
            </div>

            <!-- 표 박스: 이 영역에서만 세로 스크롤 -->
            <div class="evidence-wrap">
              <table class="table table-sm table-bordered align-middle evidence-table">
                <thead class="table-light">
                  <tr>
                    <th style="min-width:120px;">S/N</th>
                    <th class="text-end" style="min-width:100px;">나이(h)</th>
                    <th class="text-end" style="min-width:90px;">β(형상)</th>
                    <th class="text-end" style="min-width:90px;">η(척도)</th>
                    <th class="text-end" style="min-width:140px;">P(다음 H일, %)</th>
                  </tr>
                </thead>
                <tbody id="${safe}-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>`;

    // 탭 DOM이 그려진 뒤: 렌더 + 이벤트 연결
    setTimeout(() => {
      const selH = document.getElementById(`${safe}-horizon`);
      const inpP = document.getElementById(`${safe}-minpct`);
      const btnC = document.getElementById(`${safe}-csv`);
      const tbodyId = `${safe}-tbody`;

      if (!selH || !inpP || !btnC) return;

      // 초기값: 백엔드 horizonDaysDefault 반영
      if ([30, 60, 90, 180].includes(Number(horizonDaysDefault))) {
        selH.value = String(horizonDaysDefault);
      }

      const render = () => {
        const used = renderProbabilityTable(
          tbodyId,
          rowsAll,
          Number(selH.value),
          Number(inpP.value)
        );
        // used: 현재 화면에 표시 중인 정렬/필터 결과 — CSV에서 사용
        btnC.onclick = () => downloadEvidenceCSV(partId, used);
      };

      selH.addEventListener("change", render);
      inpP.addEventListener("input", render);
      render(); // 최초 1회
    }, 0);
  });

  nav += `</ul>`;
  panes += `</div>`;
  return nav + panes;
}

/* 확률표 렌더러 — 반환값: 화면에 표시된 행 배열( CSV 다운로드에 사용 ) */
function renderProbabilityTable(tbodyId, rowsRaw, horizonDays, minPercent) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return [];

  const H = Math.max(1, Number(horizonDays) || 90) * 24; // 시간
  const minP = Math.max(0, Number(minPercent) || 0) / 100.0; // 0~1

  const rows = (rowsRaw || [])
    .map((r) => {
      const a = Number(r.age_hours ?? 0);
      const eta = Number(r.eta ?? 0);
      const beta = Number(r.beta ?? 0);
      const p = weibullProbNext(a, eta, beta, H); // 0~1
      return { sn: r.serial || "", age: a, beta, eta, p };
    })
    .filter((r) => r.p >= minP)
    .sort((a, b) => b.p - a.p); // 확률 내림차순

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">표시할 데이터가 없습니다.</td></tr>`;
    return [];
  }

  tbody.innerHTML = rows
    .map(
      (r) => `
    <tr>
      <td>${r.sn}</td>
      <td class="text-end">${r.age.toLocaleString("ko-KR")}</td>
      <td class="text-end">${r.beta}</td>
      <td class="text-end">${r.eta.toLocaleString("ko-KR")}</td>
      <td class="text-end">${(r.p * 100).toFixed(2)} %</td>
    </tr>
  `
    )
    .join("");

  return rows; // 현재 화면 상태를 반환
}

/* CSV 다운로드 */
function downloadEvidenceCSV(partId, rows) {
  const header = [
    "part_id",
    "serial",
    "age_hours",
    "beta",
    "eta",
    "prob_percent",
  ];
  const lines = [header.join(",")].concat(
    rows.map((r) =>
      [
        `"${String(partId).replace(/"/g, '""')}"`,
        `"${String(r.sn).replace(/"/g, '""')}"`,
        r.age,
        r.beta,
        r.eta,
        (r.p * 100).toFixed(2),
      ].join(",")
    )
  );
  const blob = new Blob([lines.join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `evidence_${partId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* Weibull */
function weibullCDF(t, eta, beta) {
  if (!(eta > 0) || !(beta > 0) || !(t > 0)) return 0;
  const x = Math.min(Math.max(Math.pow(t / eta, beta), 0), 700);
  return 1 - Math.exp(-x);
}
function weibullProbNext(ageHours, eta, beta, horizonHours) {
  const a = Math.max(0, Number(ageHours) || 0);
  const H = Math.max(1, Number(horizonHours) || 1);
  const F1 = weibullCDF(a + H, eta, beta);
  const F0 = weibullCDF(a, eta, beta);
  return Math.max(0, Math.min(1, F1 - F0));
}

/* evidence 표 전용 CSS를 JS로 주입(HTML 수정 없이 v-scroll 동작 보장) */
function ensureEvidenceStyles() {
  if (document.getElementById("evidence-style")) return;
  const css = `
  .evidence-wrap{
    height:420px; overflow-y:auto; overflow-x:auto;
    -webkit-overflow-scrolling:touch; border:1px solid #dee2e6;
    border-radius:.5rem; background:#fff;
  }
  .evidence-table{ width:max-content; min-width:100%; margin-bottom:0; table-layout:fixed; }
  .evidence-table th,.evidence-table td{ white-space:nowrap; }
  .evidence-table thead th{ position:sticky; top:0; z-index:5; background:#fff; }
  `;
  const style = document.createElement("style");
  style.id = "evidence-style";
  style.textContent = css;
  document.head.appendChild(style);
}

/* ---------- 2) 지난 1년 교체 비용 차트 ---------- */
async function loadReplacementCostChart() {
  const canvas = document.getElementById("replacementCostChart");
  if (!canvas) return;
  try {
    const data = await fetchData("/api/cost/replacement_last_year");
    const ctx = canvas.getContext("2d");
    if (replacementCostChart) replacementCostChart.destroy();

    replacementCostChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "교체 비용 (원)",
            data: data.data,
            backgroundColor: "rgba(255, 99, 132, 0.7)",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: (c) => `${c.label}: ${fmtWon(c.raw)}` },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: (v) => v.toLocaleString("ko-KR") + "원" },
          },
        },
      },
    });
  } catch (e) {
    console.error(e);
  }
}

/* ---------- 3) 예방 정비 우선순위: 검색/정렬/CSV ---------- */
async function loadPriorityMaintenance() {
  const section = document.getElementById("pm-priority-section");
  if (!section) return;

  section.innerHTML = `
    <div class="d-flex justify-content-between align-items-center mb-2">
      <div class="input-group" style="max-width: 320px;">
        <span class="input-group-text">검색</span>
        <input id="pm-search" class="form-control" placeholder="부품/시리얼/중요도 검색">
      </div>
      <div>
        <button id="pm-download" class="btn btn-outline-secondary btn-sm">CSV 다운로드</button>
      </div>
    </div>
    <div class="table-responsive">
      <table id="pm-table" class="table table-hover align-middle">
        <thead class="table-light">
          <tr>
            <th data-key="rank"           class="sortable">우선순위</th>
            <th data-key="part_id"        class="sortable">부품 (S/N)</th>
            <th data-key="priority"       class="sortable">중요도</th>
            <th data-key="usage_ratio"    class="sortable">B10 수명 사용률</th>
            <th data-key="risk_score"     class="sortable">위험 점수</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>`;

  try {
    const raw = await fetchData("/api/priority_maintenance");
    let rows = (raw || []).map((r, i) => ({ ...r, rank: i + 1 }));

    const tbody = section.querySelector("#pm-table tbody");
    const searchInput = section.querySelector("#pm-search");
    const btnCsv = section.querySelector("#pm-download");
    let sortKey = "rank";
    let sortDir = "asc";

    function badge(priority) {
      if (priority === "높음")
        return `<span class="badge bg-danger">높음</span>`;
      if (priority === "중간")
        return `<span class="badge bg-warning text-dark">중간</span>`;
      return `<span class="badge bg-secondary">낮음</span>`;
    }
    function render(list) {
      tbody.innerHTML = "";
      list.forEach((r, idx) => {
        const usage = Math.max(0, Math.min(999, r.usage_ratio | 0)); // 0~999%
        tbody.insertAdjacentHTML(
          "beforeend",
          `
          <tr>
            <td class="fw-bold">${idx + 1}</td>
            <td>${r.part_id}<br><small class="text-muted">${
            r.serial_number ?? ""
          }</small></td>
            <td>${badge(r.priority)}</td>
            <td>
              <div class="progress" style="height:20px;">
                <div class="progress-bar ${
                  usage >= 90 ? "bg-danger" : "bg-warning text-dark"
                }" role="progressbar"
                     style="width:${Math.min(usage, 100)}%;">${usage}%</div>
              </div>
            </td>
            <td class="fw-bold">${Number(r.risk_score || 0).toFixed(2)} 점</td>
          </tr>`
        );
      });
    }
    function apply() {
      const q = (searchInput.value || "").trim().toLowerCase();
      let list = rows.filter((r) =>
        [r.part_id, r.serial_number, r.priority]
          .join(" ")
          .toLowerCase()
          .includes(q)
      );
      list.sort((a, b) => {
        const A = a[sortKey],
          B = b[sortKey];
        if (typeof A === "number" && typeof B === "number")
          return sortDir === "asc" ? A - B : B - A;
        return sortDir === "asc"
          ? String(A).localeCompare(String(B))
          : String(B).localeCompare(String(A));
      });
      render(list);
    }

    // 정렬 이벤트
    section.querySelectorAll("th.sortable").forEach((th) => {
      th.style.cursor = "pointer";
      th.addEventListener("click", () => {
        const key = th.dataset.key;
        if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
        else {
          sortKey = key;
          sortDir = "asc";
        }
        apply();
      });
    });

    // 검색 이벤트
    searchInput.addEventListener("input", () => apply());

    // CSV 다운로드
    btnCsv.addEventListener("click", () => {
      const header = [
        "rank",
        "part_id",
        "serial_number",
        "priority",
        "usage_ratio",
        "risk_score",
      ];
      const csv = [header.join(",")]
        .concat(rows.map((r) => header.map((k) => r[k] ?? "").join(",")))
        .join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "priority_maintenance.csv";
      a.click();
      URL.revokeObjectURL(url);
    });

    apply(); // 최초 렌더
  } catch (e) {
    console.error(e);
    section.innerHTML = `<div class="alert alert-danger">우선순위 목록을 불러오는 중 오류가 발생했습니다.</div>`;
  }
}
