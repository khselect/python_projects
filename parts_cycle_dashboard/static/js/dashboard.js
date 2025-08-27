// DOM이 완전히 로드된 후, 페이지 경로에 맞는 기능만 실행하도록 구조를 통합합니다.
document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname;

  if (path === "/analysis-view") {
    fetchAnalysisData();
  } else if (path === "/dashboard") {
    initializeDashboardTabs();
  }
});

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
    destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "pie",
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.data,
            backgroundColor: [
              "#0d6efd",
              "#6c757d",
              "#198754",
              "#dc3545",
              "#ffc107",
              "#0dcaf0",
            ],
          },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  });
}

function loadFailureRankingChart() {
  fetchData("/api/failure_ranking").then((data) => {
    const canvasId = "failureRankingChart";
    destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { label: "고장 횟수", data: data.data, backgroundColor: "#dc3545" },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
      },
    });
  });
}

function loadInstallationTrendChart() {
  fetchData("/api/installation_trend").then((data) => {
    const canvasId = "installationTrendChart";
    destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

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
            borderColor: "#0d6efd",
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
      },
    });
  });
}

function loadFailureLifespanRatioChart() {
  fetchData("/api/failure_lifespan_ratio").then((data) => {
    const canvasId = "timeToFailureChart";
    destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

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
            backgroundColor: "#6f42c1",
          },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: "y" },
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
      const container = document.getElementById(canvasId).parentElement;
      if (container)
        container.innerHTML =
          '<p class="text-center text-muted mt-5">히트맵으로 표시할 고장 데이터가 없습니다.</p>';
      return;
    }

    new Chart(ctx, {
      type: "matrix",
      data: {
        datasets: [
          {
            label: "월별 고장 횟수",
            data: data.dataset,
            backgroundColor: (c) => {
              const v = c.raw?.v ?? 0;
              return `rgba(220, 53, 69, ${v > 0 ? 0.2 + v / 5 : 0.1})`;
            },
            borderColor: "grey",
            borderWidth: 1,
            // ▼▼▼ [수정] chart.chartArea가 없을 경우를 대비하여 방어 코드 추가 ▼▼▼
            width: ({ chart }) =>
              (chart.chartArea || {}).width / data.x_labels.length - 1,
            height: ({ chart }) =>
              (chart.chartArea || {}).height / data.y_labels.length - 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            type: "category",
            labels: data.x_labels,
            grid: { display: false },
          },
          y: {
            type: "category",
            labels: data.y_labels,
            grid: { display: false },
            offset: true,
          },
        },
      },
    });
  });
}

function loadFailureRateTrendChart() {
  fetchData("/api/failure_rate_trend").then((data) => {
    const canvasId = "failureRateTrendChart";
    destroyExistingChart(canvasId); // ▼▼▼ [수정 2] 기존 차트 파괴 로직 추가 ▼▼▼

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
            borderColor: "#dc3545",
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
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
