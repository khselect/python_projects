// cost_analysis.js

document.addEventListener("DOMContentLoaded", function () {
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

/* ---------- 1) 고장 예측 기반 예산 계획 ---------- */
function loadBudgetForecast() {
  const forecastSection = document.getElementById("budget-forecast-section");
  if (!forecastSection) return;

  fetchData("/api/cost/budget_forecast")
    .then((data) => {
      if (data.error) {
        forecastSection.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류 발생: ${data.error}</div>`;
        return;
      }
      
      const totalCost = data.total_forecast_cost || 0;
      const forecastDetails = data.forecast_details || {};
      
      const tabsHtml = buildPartTabs(
        forecastDetails,
        data.explain || [],
        data.assumptions?.horizon_days
      );

      // 메인 예측 정보 UI 렌더링
      forecastSection.innerHTML = `
        <div class="col-md-5 mb-3 mb-md-0">
          <div class="card kpi-card h-100">
            <div class="card-body d-flex flex-column">
              <div>
                <div class="d-flex justify-content-between align-items-center">
                  <h5 class="text-muted mb-0">총 예상 교체 비용 (향후 90일)</h5>
                  <i class="bi bi-info-circle" 
                     data-bs-toggle="tooltip" 
                     data-bs-placement="top"
                     title="과거 교체 이력과 수명 데이터를 분석하여, 향후 90일 내 고장 가능성이 높은 부품들의 예상 교체 비용 총합입니다.">
                  </i>
                </div>
                <div class="kpi-value text-primary mt-2">${fmtWon(totalCost)}</div>
              </div>
              <hr>
              <div class="flex-grow-1 d-flex flex-column">
                  <h6 class="text-muted">부품별 예상 비용 기여도</h6>
                  <div class="chart-container flex-grow-1 p-0" style="min-height: 250px;">
                      <canvas id="forecastContributionChart"></canvas>
                  </div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-7">
          ${tabsHtml}
        </div>`;

      // ⭐️ 추가: '예상 비용 산출 방식' 설명 카드 HTML
      const explanationHtml = `
      <div class="card mb-4">
        <div class="card-header">
            <h3>예상 비용 산출 방식</h3>
        </div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-lg-4">
                    <div class="p-3 rounded h-100" style="background-color: #e7f1ff; border-left: 5px solid #0d6efd;">
                        <p class="fw-bold text-primary mb-1">1. 개별 부품 고장 확률 예측</p>
                        <p class="mb-0 small">가동 중인 모든 부품(S/N 기준)의 현재 나이(h)와 과거 수명 데이터를 기반으로, 향후 예측 기간(예: 90일) 내에 고장날 확률(P)을 통계적으로 계산합니다.</p>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="p-3 rounded h-100" style="background-color: #e5f7ef; border-left: 5px solid #198754;">
                        <p class="fw-bold text-success mb-1">2. 부품 유형별 예상 교체 수량 산정</p>
                        <p class="mb-1 small">동일한 부품 유형(예: DCU)에 속하는 모든 개별 부품들의 고장 확률을 합산하여, 해당 유형의 최종 '예상 교체 수량'을 산출합니다.</p>
                        <small class="text-muted fst-italic">산술식: 예상 교체 수량 = Σ P (개별 부품들의 고장 확률 합)</small>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="p-3 rounded h-100" style="background-color: #fff8e1; border-left: 5px solid #ffc107;">
                        <p class="fw-bold text-warning mb-1">3. 총 예상 비용 계산</p>
                        <p class="mb-1 small">산출된 부품 유형별 '예상 교체 수량'에 해당 부품의 '평균 단가'를 곱하여 비용을 계산하고, 모든 부품 유형의 비용을 합산하여 최종 '총 예상 교체 비용'을 도출합니다.</p>
                        <small class="text-muted fst-italic">산술식: 총 예상 비용 = Σ (부품 유형별 예상 교체 수량 × 평균 단가)</small>
                    </div>
                </div>
            </div>
        </div>
      </div>
      `;

      // ⭐️ 추가: 메인 예산 계획 카드 바로 뒤에 설명 카드 삽입
      const parentCard = forecastSection.closest('.card');
      if (parentCard) {
        parentCard.insertAdjacentHTML('afterend', explanationHtml);
      }


      // 비용 기여도 차트 생성 로직
      const partLabels = Object.keys(forecastDetails);
      if (partLabels.length > 0) {
        const costData = partLabels.map(partId => forecastDetails[partId].total_cost);
        const sortedData = partLabels.map((label, index) => ({
          label,
          cost: costData[index]
        })).sort((a, b) => a.cost - b.cost);

        const ctx = document.getElementById('forecastContributionChart').getContext('2d');
        new Chart(ctx, {
          type: 'bar',
          data: {
            labels: sortedData.map(d => d.label),
            datasets: [{
              label: '예상 비용',
              data: sortedData.map(d => d.cost),
              backgroundColor: 'rgba(54, 162, 235, 0.7)',
            }]
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: { callbacks: { label: (c) => ` ${fmtWon(c.raw)}` } }
            },
            scales: {
              x: {
                beginAtZero: true,
                ticks: { callback: (v) => `${(v / 10000).toLocaleString('ko-KR')}만` }
              }
            }
          }
        });
      }

      // Bootstrap 툴팁 활성화
      const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
      });

    })
    .catch((error) => {
      console.error("Error loading budget forecast:", error);
      forecastSection.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류가 발생했습니다.</div>`;
    });
}


/* ... buildPartTabs, renderProbabilityTable 등 나머지 함수들은
   이전 답변('상위 N개 표시'로 수정한 버전)과 동일하게 유지합니다 ...
*/
/* 부품 탭 + 확률표(%) + 상위 N개 필터 + CSV */
function buildPartTabs(details, explainRows, horizonDaysDefault) {
  const won = (v) => (v ?? 0).toLocaleString("ko-KR") + " 원";
  const n2 = (v) => Number(v ?? 0).toFixed(2);

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

    const rowsAll = (explainByPart[partId] || []).slice();

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
                <span class="input-group-text">예측 기간</span>
                <select class="form-select" id="${safe}-horizon">
                  <option value="30">30일</option>
                  <option value="60">60일</option>
                  <option value="90" selected>90일</option>
                  <option value="180">180일</option>
                </select>
              </div>
              <div class="input-group input-group-sm" style="width: 180px;">
                <span class="input-group-text">상위 N개 표시</span>
                <input class="form-control" id="${safe}-topn" type="number" step="5" min="5" value="10">
              </div>
              <button id="${safe}-csv" class="btn btn-outline-secondary btn-sm">CSV 다운로드</button>
            </div>
            <div class="evidence-wrap">
              <table class="table table-sm table-bordered align-middle evidence-table">
                <thead class="table-light">
                  <tr>
                    <th style="min-width:120px;">S/N</th>
                    <th class="text-end" style="min-width:100px;">나이(h)</th>
                    <th class="text-end" style="min-width:90px;">β(형상)</th>
                    <th class="text-end" style="min-width:90px;">η(척도)</th>
                    <th class="text-end" style="min-width:140px;">고장확률 P (%)</th>
                  </tr>
                </thead>
                <tbody id="${safe}-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>`;

    setTimeout(() => {
      const selH = document.getElementById(`${safe}-horizon`);
      const inpN = document.getElementById(`${safe}-topn`);
      const btnC = document.getElementById(`${safe}-csv`);
      const tbodyId = `${safe}-tbody`;

      if (!selH || !inpN || !btnC) return;

      if ([30, 60, 90, 180].includes(Number(horizonDaysDefault))) {
        selH.value = String(horizonDaysDefault);
      }

      const render = () => {
        const used = renderProbabilityTable(
          tbodyId,
          rowsAll,
          Number(selH.value),
          Number(inpN.value)
        );
        btnC.onclick = () => downloadEvidenceCSV(partId, used);
      };

      selH.addEventListener("change", render);
      inpN.addEventListener("input", render);
      render();
    }, 0);
  });

  nav += `</ul>`;
  panes += `</div>`;
  return nav + panes;
}

function renderProbabilityTable(tbodyId, rowsRaw, horizonDays, topN) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return [];

  const H = Math.max(1, Number(horizonDays) || 90) * 24;
  const N = Math.max(1, Number(topN) || 10);

  const rows = (rowsRaw || [])
    .map((r) => {
      const a = Number(r.age_hours ?? 0);
      const eta = Number(r.eta ?? 0);
      const beta = Number(r.beta ?? 0);
      const p = weibullProbNext(a, eta, beta, H);
      return { sn: r.serial || "", age: a, beta, eta, p };
    })
    .sort((a, b) => b.p - a.p)
    .slice(0, N);

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
      <td class="text-end fw-bold">${(r.p * 100).toFixed(2)} %</td>
    </tr>
  `
    )
    .join("");

  return rows;
}

function downloadEvidenceCSV(partId, rows) {
  const header = ["part_id", "serial", "age_hours", "beta", "eta", "prob_percent"];
  const lines = [header.join(",")].concat(
    rows.map((r) =>
      [
        `"${String(partId).replace(/"/g, '""')}"`,
        `"${String(r.sn).replace(/"/g, '""')}"`,
        r.age, r.beta, r.eta, (r.p * 100).toFixed(2),
      ].join(",")
    )
  );
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `evidence_${partId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

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
  return Math.max(0, Math.min(1, (F1 - F0) / (1 - F0)));
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
        datasets: [{
          label: "교체 비용 (원)",
          data: data.data,
          backgroundColor: "rgba(255, 99, 132, 0.7)",
        }, ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => `${c.label}: ${fmtWon(c.raw)}` } },
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
            <th data-key="rank" class="sortable">우선순위</th>
            <th data-key="part_id" class="sortable">부품 (S/N)</th>
            <th data-key="priority" class="sortable">중요도</th>
            <th data-key="usage_ratio" class="sortable">B10 수명 사용률</th>
            <th data-key="risk_score" class="sortable">위험 점수</th>
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
      if (priority === "높음") return `<span class="badge bg-danger">높음</span>`;
      if (priority === "중간") return `<span class="badge bg-warning text-dark">중간</span>`;
      return `<span class="badge bg-secondary">낮음</span>`;
    }
    function render(list) {
      tbody.innerHTML = "";
      list.forEach((r, idx) => {
        const usage = Math.max(0, Math.min(999, r.usage_ratio | 0));
        tbody.insertAdjacentHTML(
          "beforeend",
          `<tr>
            <td class="fw-bold">${idx + 1}</td>
            <td>${r.part_id}<br><small class="text-muted">${r.serial_number ?? ""}</small></td>
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
        const A = a[sortKey], B = b[sortKey];
        if (typeof A === "number" && typeof B === "number")
          return sortDir === "asc" ? A - B : B - A;
        return sortDir === "asc" ?
          String(A).localeCompare(String(B)) :
          String(B).localeCompare(String(A));
      });
      render(list);
    }
    
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

    searchInput.addEventListener("input", () => apply());

    btnCsv.addEventListener("click", () => {
      const header = ["rank", "part_id", "serial_number", "priority", "usage_ratio", "risk_score"];
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

    apply();
  } catch (e) {
    console.error(e);
    section.innerHTML = `<div class="alert alert-danger">우선순위 목록을 불러오는 중 오류가 발생했습니다.</div>`;
  }
}