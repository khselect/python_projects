// DOM이 완전히 로드된 후, 페이지 경로에 맞는 기능만 실행하도록 구조를 통합합니다.
document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname;

  if (window.ChartDataLabels) {
    Chart.register(ChartDataLabels);
    Chart.defaults.set("plugins.datalabels", { display: false });
  }

  if (path === "/analysis-view") {
    fetchAnalysisData();
  } else if (path === "/dashboard") {
    initializeDashboardTabs();
  }
});

// --- 대시보드 공용 색상 팔레트 (colorblind-safe, validated) ---
const PALETTE = {
  blue: "#2a78d6",
  aqua: "#1baf7a",
  yellow: "#eda100",
  green: "#008300",
  violet: "#4a3aa7",
  red: "#e34948",
  magenta: "#e87ba4",
  orange: "#eb6834",
};
const CATEGORICAL_ORDER = [
  PALETTE.blue,
  PALETTE.aqua,
  PALETTE.yellow,
  PALETTE.green,
  PALETTE.violet,
  PALETTE.red,
  PALETTE.magenta,
  PALETTE.orange,
];
const INK = {
  primary: "#0b0b0b",
  secondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
};
const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

/**
 * 숫자를 한국어 로케일 형식으로 포맷합니다.
 */
function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Number(value).toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

/**
 * KPI 스탯 타일 행을 렌더링합니다.
 * @param {string} containerId - 타일을 렌더링할 컨테이너 id
 * @param {Array<{label:string, value:string, unit?:string, sub?:string, subDirection?:'up'|'down', accent?:string}>} items
 */
function renderKpiRow(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = items
    .map((item) => {
      const accentClass = item.accent ? `accent-${item.accent}` : "";
      const subClass = item.subDirection ? item.subDirection : "";
      const subHtml = item.sub
        ? `<div class="stat-tile-sub ${subClass}">${item.sub}</div>`
        : "";
      const unitHtml = item.unit
        ? `<span class="unit">${item.unit}</span>`
        : "";
      return `
        <div class="col-6 col-lg-3">
          <div class="stat-tile ${accentClass}">
            <div class="stat-tile-label">${item.label}</div>
            <div class="stat-tile-value">${item.value}${unitHtml}</div>
            ${subHtml}
          </div>
        </div>`;
    })
    .join("");
}

/**
 * API로부터 데이터를 비동기적으로 가져오는 공통 함수
 */
async function fetchData(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return await response.json();
}

// --- '/dashboard' (종합 대시보드) 페이지 전용 함수들 ---

/**
 * 대시보드 탭 기능을 초기화하고, 각 탭에 맞는 차트 로드 이벤트를 설정합니다.
 */
function initializeDashboardTabs() {
  const chartLoadFunctions = {
    "dist-tab": loadPartDistributionChart,
    "rank-tab": loadFailureRankingChart,
    "heatmap-tab": loadFailureHeatmapChart,
    "install-tab": loadInstallationTrendChart,
    "ratio-tab": loadFailureLifespanRatioChart,
    "trend-tab": loadFailureRateTrendChart,
  };

  const tabButtons = document.querySelectorAll("#dashboard-tabs .nav-link");

  tabButtons.forEach((button) => {
    // ▼▼▼ [수정 1] 'show.bs.tab' -> 'shown.bs.tab'으로 변경 ▼▼▼
    // 탭이 완전히 화면에 표시된 "후에" 차트를 그리도록 이벤트를 변경합니다.
    button.addEventListener("shown.bs.tab", function (event) {
      const functionToLoad = chartLoadFunctions[event.target.id];
      if (functionToLoad) {
        functionToLoad();
      }
    });
  });

  // 페이지가 처음 로드되었을 때 활성화된 탭의 차트를 즉시 로드합니다.
  const activeTab = document.querySelector("#dashboard-tabs .nav-link.active");
  if (activeTab) {
    const initialFunction = chartLoadFunctions[activeTab.id];
    if (initialFunction) {
      initialFunction();
    }
  }
}

/**
 * 캔버스에 이미 차트가 있는지 확인하고, 있으면 파괴하는 헬퍼 함수
 * @param {string} canvasId - 캔버스 요소의 ID
 */
function destroyExistingChart(canvasId) {
  const existingChart = Chart.getChart(canvasId);
  if (existingChart) {
    existingChart.destroy();
  }
}

function loadPartDistributionChart() {
  fetchData("/api/part_distribution").then((data) => {
    const canvasId = "partDistributionChart";
    destroyExistingChart(canvasId);

    const total = data.data.reduce((sum, v) => sum + v, 0);
    const maxIdx = data.data.indexOf(Math.max(...data.data));

    renderKpiRow("dist-kpis", [
      { label: "총 부품 수", value: formatNumber(total), unit: "개", accent: "blue" },
      {
        label: "부품 유형 수",
        value: formatNumber(data.labels.length),
        unit: "종",
        accent: "blue",
      },
      {
        label: "최다 사용 부품",
        value: data.labels[maxIdx] ?? "-",
        sub: total ? `전체의 ${((data.data[maxIdx] / total) * 100).toFixed(1)}%` : "",
        accent: "violet",
      },
    ]);

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.data,
            backgroundColor: CATEGORICAL_ORDER.slice(0, data.labels.length),
            borderColor: "#fff",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "55%",
        plugins: {
          legend: {
            position: "right",
            labels: { color: INK.secondary, padding: 14 },
          },
          datalabels: {
            display: (ctx) => {
              const value = ctx.dataset.data[ctx.dataIndex];
              return total > 0 && value / total >= 0.05;
            },
            color: "#fff",
            font: { weight: "bold" },
            formatter: (value) => `${((value / total) * 100).toFixed(0)}%`,
          },
        },
      },
    });
  });
}

function loadFailureRankingChart() {
  fetchData("/api/failure_ranking").then((data) => {
    const canvasId = "failureRankingChart";
    destroyExistingChart(canvasId);

    const total = data.data.reduce((sum, v) => sum + v, 0);

    renderKpiRow("rank-kpis", [
      { label: "총 고장 건수", value: formatNumber(total), unit: "건", accent: "red" },
      {
        label: "최다 고장 부품",
        value: data.labels[0] ?? "-",
        sub: data.data[0] ? `${formatNumber(data.data[0])}건` : "",
        accent: "red",
      },
      {
        label: "고장 발생 부품 종류",
        value: formatNumber(data.labels.length),
        unit: "종",
        accent: "blue",
      },
    ]);

    // 최다 고장 부품(1위)만 강조색, 나머지는 차분한 계열로 처리 (emphasis 패턴)
    const barColors = data.data.map((_, i) =>
      i === 0 ? STATUS.critical : "rgba(42, 120, 214, 0.55)"
    );

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { label: "고장 횟수", data: data.data, backgroundColor: barColors },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: INK.grid },
          },
          x: { grid: { display: false } },
        },
        plugins: {
          legend: { display: false },
          datalabels: {
            display: true,
            anchor: "end",
            align: "top",
            color: INK.secondary,
            font: { weight: "bold" },
            formatter: (value) => formatNumber(value),
          },
        },
      },
    });
  });
}

function loadInstallationTrendChart() {
  fetchData("/api/installation_trend").then((data) => {
    const canvasId = "installationTrendChart";
    destroyExistingChart(canvasId);

    const total = data.data.reduce((sum, v) => sum + v, 0);
    const lastIdx = data.data.length - 1;
    const maxIdx = data.data.indexOf(Math.max(...data.data));

    renderKpiRow("install-kpis", [
      { label: "총 설치 대수", value: formatNumber(total), unit: "대", accent: "blue" },
      {
        label: "최근월 설치",
        value: lastIdx >= 0 ? formatNumber(data.data[lastIdx]) : "-",
        unit: "대",
        sub: lastIdx >= 0 ? data.labels[lastIdx] : "",
        accent: "blue",
      },
      {
        label: "설치 최다 월",
        value: maxIdx >= 0 ? data.labels[maxIdx] : "-",
        sub: maxIdx >= 0 ? `${formatNumber(data.data[maxIdx])}대` : "",
        accent: "violet",
      },
    ]);

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "설치 건수",
            data: data.data,
            borderColor: PALETTE.blue,
            backgroundColor: "rgba(42, 120, 214, 0.12)",
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: PALETTE.blue,
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: INK.grid },
          },
          x: { grid: { display: false } },
        },
        plugins: { legend: { display: false } },
      },
    });
  });
}

function loadFailureLifespanRatioChart() {
  fetchData("/api/failure_lifespan_ratio").then((data) => {
    const canvasId = "timeToFailureChart";
    destroyExistingChart(canvasId);

    // API가 오름차순 정렬되어 있으므로, 최고 비율은 마지막 항목입니다.
    const worstIdx = data.data.length - 1;
    const avgRatio =
      data.data.length > 0
        ? data.data.reduce((sum, v) => sum + v, 0) / data.data.length
        : 0;

    renderKpiRow("ratio-kpis", [
      {
        label: "평균 고장 수명 비율",
        value: avgRatio.toFixed(1),
        unit: "%",
        accent: "violet",
      },
      {
        label: "최고 비율 부품",
        value: worstIdx >= 0 ? data.labels[worstIdx] : "-",
        sub: worstIdx >= 0 ? `${data.data[worstIdx].toFixed(1)}%` : "",
        accent: "red",
      },
      {
        label: "최저 비율 부품",
        value: data.labels[0] ?? "-",
        sub: data.data[0] !== undefined ? `${data.data[0].toFixed(1)}%` : "",
        accent: "green",
      },
    ]);

    // 가장 취약한(비율이 높은) 부품만 강조색으로 표시 (emphasis 패턴)
    const barColors = data.data.map((_, i) =>
      i === worstIdx ? STATUS.critical : "rgba(74, 58, 167, 0.6)"
    );

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "고장 수명 비율 (%)",
            data: data.data,
            backgroundColor: barColors,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: INK.grid },
            ticks: { callback: (v) => `${v}%` },
          },
          y: { grid: { display: false } },
        },
        plugins: {
          legend: { display: false },
          datalabels: {
            display: true,
            anchor: "end",
            align: "end",
            color: INK.secondary,
            font: { weight: "bold" },
            formatter: (value) => `${value.toFixed(1)}%`,
          },
        },
      },
    });
  });
}

// function loadFailureHeatmapChart() {
//   fetchData("/api/failure_heatmap").then((data) => {
//     const canvasId = "lifespanDistributionChart";
//     destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

//     const ctx = document.getElementById(canvasId)?.getContext("2d");
//     if (!ctx) return;
//     if (
//       !data ||
//       !data.dataset ||
//       data.dataset.length === 0 ||
//       !data.x_labels ||
//       data.x_labels.length === 0 ||
//       !data.y_labels ||
//       data.y_labels.length === 0
//     ) {
//       const container = document.getElementById(canvasId).parentElement;
//       if (container)
//         container.innerHTML =
//           '<p class="text-center text-muted mt-5">히트맵으로 표시할 고장 데이터가 없습니다.</p>';
//       return;
//     }
//     new Chart(ctx, {
//       type: "matrix",
//       data: {
//         datasets: [
//           {
//             label: "월별 고장 횟수",
//             data: data.dataset,
//             backgroundColor: (c) => {
//               const v = c.raw?.v ?? 0;
//               return `rgba(220, 53, 69, ${v > 0 ? 0.2 + v / 5 : 0.1})`;
//             },
//             borderColor: "grey",
//             borderWidth: 1,
//             width: ({ chart }) =>
//               chart.chartArea.width / data.x_labels.length - 1,
//             height: ({ chart }) =>
//               chart.chartArea.height / data.y_labels.length - 1,
//           },
//         ],
//       },
//       options: {
//         responsive: true,
//         maintainAspectRatio: false,
//         plugins: { legend: { display: false } },
//         scales: {
//           x: {
//             type: "category",
//             labels: data.x_labels,
//             grid: { display: false },
//           },
//           y: {
//             type: "category",
//             labels: data.y_labels,
//             grid: { display: false },
//             offset: true,
//           },
//         },
//       },
//     });
//   });
// }

function loadFailureHeatmapChart() {
  fetchData("/api/failure_heatmap").then((data) => {
    const canvasId = "lifespanDistributionChart";
    destroyExistingChart(canvasId);

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;

    if (
      !data ||
      !data.dataset ||
      data.dataset.length === 0 ||
      !data.x_labels ||
      data.x_labels.length === 0 ||
      !data.y_labels ||
      data.y_labels.length === 0
    ) {
      renderKpiRow("heatmap-kpis", []);
      const container = document.getElementById(canvasId).parentElement;
      if (container)
        container.innerHTML =
          '<p class="text-center text-muted mt-5">히트맵으로 표시할 고장 데이터가 없습니다.</p>';
      return;
    }

    const totalFailures = data.dataset.reduce((sum, d) => sum + d.v, 0);
    const maxCell = data.dataset.reduce(
      (max, d) => (d.v > max.v ? d : max),
      data.dataset[0]
    );
    const byPart = {};
    data.dataset.forEach((d) => {
      byPart[d.y] = (byPart[d.y] || 0) + d.v;
    });
    const topPart = Object.entries(byPart).sort((a, b) => b[1] - a[1])[0];

    renderKpiRow("heatmap-kpis", [
      {
        label: "총 고장 건수",
        value: formatNumber(totalFailures),
        unit: "건",
        accent: "red",
      },
      {
        label: "최다 발생 부품",
        value: topPart ? topPart[0] : "-",
        sub: topPart ? `${formatNumber(topPart[1])}건` : "",
        accent: "red",
      },
      {
        label: "최다 발생 시점",
        value: maxCell ? `${maxCell.y} · ${maxCell.x}` : "-",
        sub: maxCell ? `${formatNumber(maxCell.v)}건 집중` : "",
        accent: "violet",
      },
    ]);

    const maxV = maxCell ? maxCell.v : 1;

    new Chart(ctx, {
      type: "matrix",
      data: {
        datasets: [
          {
            label: "월별 고장 횟수",
            data: data.dataset,
            backgroundColor: (c) => {
              const v = c.raw?.v ?? 0;
              if (v === 0) return "rgba(227, 73, 72, 0.06)";
              const intensity = 0.2 + 0.75 * (v / maxV);
              return `rgba(227, 73, 72, ${Math.min(intensity, 0.95)})`;
            },
            borderColor: "#fcfcfb",
            borderWidth: 2,
            width: ({ chart }) =>
              (chart.chartArea || {}).width / data.x_labels.length - 2,
            height: ({ chart }) =>
              (chart.chartArea || {}).height / data.y_labels.length - 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          datalabels: {
            display: (c) => (c.dataset.data[c.dataIndex].v ?? 0) > 0,
            color: (c) =>
              (c.dataset.data[c.dataIndex].v ?? 0) / maxV > 0.55
                ? "#fff"
                : INK.primary,
            font: { size: 11, weight: "bold" },
            formatter: (v) => v.v,
          },
        },
        scales: {
          x: {
            type: "category",
            labels: data.x_labels,
            grid: { display: false },
            ticks: { color: INK.secondary },
          },
          y: {
            type: "category",
            labels: data.y_labels,
            grid: { display: false },
            offset: true,
            ticks: { color: INK.secondary },
          },
        },
      },
    });
  });
}

function loadFailureRateTrendChart() {
  fetchData("/api/failure_rate_trend").then((data) => {
    const canvasId = "failureRateTrendChart";
    destroyExistingChart(canvasId);

    const total = data.data.reduce((sum, v) => sum + v, 0);
    const lastIdx = data.data.length - 1;
    const prevIdx = lastIdx - 1;
    let deltaValue = "-";
    let deltaSub = "";
    let deltaDirection = "";
    if (lastIdx >= 0 && prevIdx >= 0) {
      const prev = data.data[prevIdx];
      const curr = data.data[lastIdx];
      const diff = curr - prev;
      deltaDirection = diff > 0 ? "up" : diff < 0 ? "down" : "";
      const pct = prev > 0 ? ((diff / prev) * 100).toFixed(0) : null;
      deltaValue =
        diff === 0 ? "0건" : `${diff > 0 ? "▲" : "▼"} ${Math.abs(diff)}건`;
      deltaSub = `전월 대비${pct !== null ? ` (${diff > 0 ? "+" : ""}${pct}%)` : ""}`;
    }

    renderKpiRow("trend-kpis", [
      {
        label: "누적 고장 건수",
        value: formatNumber(total),
        unit: "건",
        accent: "red",
      },
      {
        label: "최근월 고장 건수",
        value: lastIdx >= 0 ? formatNumber(data.data[lastIdx]) : "-",
        unit: "건",
        sub: lastIdx >= 0 ? data.labels[lastIdx] : "",
        accent: "red",
      },
      {
        label: "전월 대비 증감",
        value: deltaValue,
        sub: deltaSub,
        subDirection: deltaDirection,
        accent: deltaDirection === "up" ? "red" : "green",
      },
    ]);

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "월별 고장 건수",
            data: data.data,
            borderColor: STATUS.critical,
            backgroundColor: "rgba(227, 73, 72, 0.12)",
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: STATUS.critical,
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: INK.grid },
          },
          x: { grid: { display: false } },
        },
        plugins: { legend: { display: false } },
      },
    });
  });
}

// --- '/analysis-view' (수명 분석) 페이지 전용 함수들 ---
// 이 부분은 변경 없이 그대로 유지됩니다.
async function fetchAnalysisData() {
  const summarySection = document.getElementById("summary-section");
  const chartTabs = document.getElementById("chart-tabs");
  const chartTabsContent = document.getElementById("chart-tabs-content");
  if (!summarySection || !chartTabs || !chartTabsContent) {
    return;
  }
  try {
    const results = await fetchData("/api/analysis_results");
    summarySection.innerHTML = "";
    chartTabs.innerHTML = "";
    chartTabsContent.innerHTML = "";
    if (Object.keys(results).length === 0) {
      summarySection.innerHTML = `<div class="alert alert-info">분석할 데이터가 없습니다.</div>`;
      return;
    }
    const summaryTable = createSummaryTable(results);
    summarySection.appendChild(summaryTable);
    let isFirstTab = true;
    for (const partId in results) {
      const data = results[partId];
      if (data.plot_data && data.plot_data.x && data.plot_data.y) {
        createChartTab(partId, data, isFirstTab);
        isFirstTab = false;
      }
    }
    if (chartTabs.innerHTML === "") {
      chartTabsContent.innerHTML =
        '<p class="text-muted">분석 가능한 그래프가 없습니다.</p>';
    }
  } catch (error) {
    summarySection.innerHTML = `<div class="alert alert-danger">분석 결과를 불러오는 중 오류가 발생했습니다.</div>`;
  }
}
function createSummaryTable(results) {
  const table = document.createElement("table");
  table.className = "table table-bordered";
  table.innerHTML = `
        <thead class="table-light">
            <tr>
                <th>부품 ID</th>
                <th>형상모수 (β)</th>
                <th>척도모수 (η, 시간)</th>
                <th>B10 수명 (시간)</th>
                <th>분석 상태</th>
            </tr>
        </thead>
        <tbody>
        ${Object.entries(results)
          .map(
            ([partId, data]) => `
            <tr>
                <td><strong>${partId}</strong></td>
                <td>${data.beta ?? "N/A"}</td>
                <td>${data.eta?.toLocaleString() ?? "N/A"}</td>
                <td>${data.b10_life?.toLocaleString() ?? "N/A"}</td>
                <td>${
                  data.error
                    ? `<span class="badge bg-warning text-dark">${data.error}</span>`
                    : '<span class="badge bg-success">분석 완료</span>'
                }</td>
            </tr>
        `
          )
          .join("")}
        </tbody>`;
  return table;
}
function createChartTab(partId, data, isActive) {
  const chartTabs = document.getElementById("chart-tabs");
  const chartTabsContent = document.getElementById("chart-tabs-content");
  const safePartId = partId.replace(/[^a-zA-Z0-9]/g, "");
  const tabItem = document.createElement("li");
  tabItem.className = "nav-item";
  tabItem.innerHTML = `<button class="nav-link ${
    isActive ? "active" : ""
  }" data-bs-toggle="tab" data-bs-target="#pane-${safePartId}" type="button">${partId}</button>`;
  chartTabs.appendChild(tabItem);
  const tabPane = document.createElement("div");
  tabPane.className = `tab-pane fade ${isActive ? "show active" : ""}`;
  tabPane.id = `pane-${safePartId}`;
  tabPane.innerHTML = `
        <div class="row mt-2">
            <div class="col-md-8">
                <div style="height:350px;"><canvas></canvas></div>
            </div>
            <div class="col-md-4">
                <table class="table table-sm table-hover table-bordered">
                    <caption class="caption-top">주요 시간별 생존 확률</caption>
                    <thead class="table-light">
                        <tr><th>시간 (h)</th><th>생존 확률 (%)</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>`;
  chartTabsContent.appendChild(tabPane);
  const tableBody = tabPane.querySelector("tbody");
  if (data.b10_life) {
    tableBody.innerHTML += `<tr><td class="fw-bold">${Math.round(
      data.b10_life
    ).toLocaleString()} (B10)</td><td class="fw-bold">90.00 %</td></tr>`;
  }
  const pointsToShow = 6;
  const step = Math.max(
    1,
    Math.floor(data.plot_data.x.length / (pointsToShow + 1))
  );
  for (let i = step; i < data.plot_data.x.length; i += step) {
    if (data.plot_data.x[i] > 0 && data.plot_data.y[i] !== null) {
      tableBody.innerHTML += `<tr><td>${Math.round(
        data.plot_data.x[i]
      ).toLocaleString()}</td><td>${(data.plot_data.y[i] * 100).toFixed(
        2
      )} %</td></tr>`;
    }
  }
  const canvas = tabPane.querySelector("canvas");
  new Chart(canvas, {
    type: "line",
    data: {
      labels: data.plot_data.x,
      datasets: [
        {
          label: "생존 확률",
          data: data.plot_data.y,
          borderColor: "rgb(75, 192, 192)",
        },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
}
