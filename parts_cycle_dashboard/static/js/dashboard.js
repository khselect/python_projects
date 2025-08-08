document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname; // 현재 페이지의 경로를 가져옵니다.

  // 메인 페이지 (/) 기능 실행
  if (path === "/") {
    if (document.getElementById("pm-watchlist-section")) {
      loadPmWatchlist();
    }
  }
  // 수명 분석 결과 페이지 (/analysis-view) 기능 실행
  else if (path === "/analysis-view") {
    if (document.getElementById("summary-section")) {
      fetchAnalysisData();
    }
  }
  // 종합 대시보드 페이지 (/dashboard) 기능 실행
  else if (path === "/dashboard") {
    if (document.getElementById("partDistributionChart")) {
      // Chart.js 플러그인이 필요할 경우 여기에 등록
      // Chart.register(ChartDataLabels);
      loadDashboardCharts();
    }
  }
});

// 대시보드 초기화 및 탭 이벤트 리스너 설정
function initializeDashboard() {
  // 필수 플러그인 등록
  if (typeof ChartDataLabels !== "undefined") {
    Chart.register(ChartDataLabels);
  }

  const chartLoadStatus = {}; // 각 차트의 로딩 상태를 추적
  const tabButtons = document.querySelectorAll("#dashboard-tabs .nav-link");

  // 첫 번째 탭(활성화된 탭)의 차트를 즉시 로드
  const activeTab = document.querySelector("#dashboard-tabs .nav-link.active");
  if (activeTab) {
    loadChartForTab(activeTab.id, chartLoadStatus);
  }

  // 각 탭 버튼에 클릭 이벤트 리스너 추가
  tabButtons.forEach((button) => {
    button.addEventListener("shown.bs.tab", function (event) {
      loadChartForTab(event.target.id, chartLoadStatus);
    });
  });
}

// 탭 ID에 맞는 차트 로드 함수를 호출하는 래퍼 함수
function loadChartForTab(tabId, chartLoadStatus) {
  if (chartLoadStatus[tabId]) {
    return; // 이미 로드된 차트는 다시 로드하지 않음
  }

  console.log(`${tabId}에 해당하는 차트를 로드합니다.`);

  switch (tabId) {
    case "dist-tab":
      loadPartDistributionChart();
      break;
    case "rank-tab":
      loadFailureRankingChart();
      break;
    case "heatmap-tab":
      loadFailureHeatmapChart();
      break;
    case "install-tab":
      loadInstallationTrendChart();
      break;
    case "ratio-tab":
      loadFailureLifespanRatioChart();
      break;
    case "trend-tab":
      loadFailureRateTrendChart();
      break;
  }
  chartLoadStatus[tabId] = true; // 로드 완료 상태로 표시
}

// --- `index.html` 용 함수들 ---

// async function loadPmWatchlist() { ... } // (내용 동일)

async function fetchAnalysisData() {
  const summarySection = document.getElementById("summary-section");
  if (!summarySection) return;

  try {
    const response = await fetch("/api/analysis_results");
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    const results = await response.json();
    updateDashboard(results);
  } catch (error) {
    console.error("🚨 분석 결과 로딩 실패:", error);
    summarySection.innerHTML = `<div class="alert alert-danger">분석 결과를 불러오는 중 오류가 발생했습니다.</div>`;
  }
}

function updateDashboard(results) {
  const summarySection = document.getElementById("summary-section");
  const chartTabs = document.getElementById("chart-tabs");
  const chartTabsContent = document.getElementById("chart-tabs-content");

  if (!summarySection || !chartTabs || !chartTabsContent) return;

  summarySection.innerHTML = "";
  chartTabs.innerHTML = "";
  chartTabsContent.innerHTML = "";

  if (Object.keys(results).length === 0) {
    summarySection.innerHTML = `<div class="alert alert-info">분석할 데이터가 없습니다.</div>`;
    return;
  }

  const summaryTable = document.createElement("table");
  summaryTable.className = "table table-bordered";
  summaryTable.innerHTML = `
        <thead class="table-light">
            <tr>
                <th>부품 ID</th>
                <th>형상모수 (β)</th>
                <th>척도모수 (η, 시간)</th>
                <th>B10 수명 (시간)</th>
                <th>분석 상태</th>
            </tr>
        </thead>
        <tbody></tbody>`;
  const summaryTbody = summaryTable.querySelector("tbody");

  let isFirstTab = true;
  for (const partId in results) {
    const data = results[partId];
    const row = summaryTbody.insertRow();
    row.innerHTML = `
            <td><strong>${partId}</strong></td>
            <td>${data.beta !== null ? data.beta : "N/A"}</td>
            <td>${data.eta !== null ? data.eta.toLocaleString() : "N/A"}</td>
            <td>${
              data.b10_life !== null ? data.b10_life.toLocaleString() : "N/A"
            }</td>
            <td>${
              data.error
                ? `<span class="badge bg-warning text-dark">${data.error}</span>`
                : '<span class="badge bg-success">분석 완료</span>'
            }</td>`;

    if (data.plot_data && data.plot_data.x && data.plot_data.y) {
      const safePartId = partId.replace(/[^a-zA-Z0-9]/g, "");
      const tabItem = document.createElement("li");
      tabItem.className = "nav-item";
      tabItem.innerHTML = `<button class="nav-link ${
        isFirstTab ? "active" : ""
      }" data-bs-toggle="tab" data-bs-target="#pane-${safePartId}" type="button">${partId}</button>`;
      chartTabs.appendChild(tabItem);

      const tabPane = document.createElement("div");
      tabPane.className = `tab-pane fade ${isFirstTab ? "show active" : ""}`;
      tabPane.id = `pane-${safePartId}`;

      const contentRow = document.createElement("div");
      contentRow.className = "row mt-2";

      const chartCol = document.createElement("div");
      chartCol.className = "col-md-8";
      const chartContainer = document.createElement("div");
      chartContainer.style.height = "350px";
      const canvas = document.createElement("canvas");
      chartContainer.appendChild(canvas);
      chartCol.appendChild(chartContainer);

      const tableCol = document.createElement("div");
      tableCol.className = "col-md-4";
      const dataTable = document.createElement("table");
      dataTable.className = "table table-sm table-hover table-bordered";
      dataTable.innerHTML = `
                <caption class="caption-top">주요 시간별 생존 확률</caption>
                <thead class="table-light">
                    <tr><th>시간 (h)</th><th>생존 확률 (%)</th></tr>
                </thead>
                <tbody></tbody>
            `;
      const tableBody = dataTable.querySelector("tbody");

      if (data.b10_life) {
        const b10Row = tableBody.insertRow();
        b10Row.innerHTML = `<td class="fw-bold">${Math.round(
          data.b10_life
        ).toLocaleString()} (B10)</td><td class="fw-bold">90.00 %</td>`;
      }

      const plotX = data.plot_data.x;
      const plotY = data.plot_data.y;
      const pointsToShow = 6;
      const step = Math.max(1, Math.floor(plotX.length / (pointsToShow + 1)));

      for (let i = step; i < plotX.length; i += step) {
        if (plotX[i] > 0 && plotY[i] !== null) {
          const tr = tableBody.insertRow();
          const time = Math.round(plotX[i]).toLocaleString();
          const prob = (plotY[i] * 100).toFixed(2);
          tr.innerHTML = `<td>${time}</td><td>${prob} %</td>`;
        }
      }
      tableCol.appendChild(dataTable);

      contentRow.appendChild(chartCol);
      contentRow.appendChild(tableCol);
      tabPane.appendChild(contentRow);
      chartTabsContent.appendChild(tabPane);

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
      isFirstTab = false;
    }
  }
  summarySection.appendChild(summaryTable);
  if (chartTabs.innerHTML === "") {
    chartTabsContent.innerHTML =
      '<p class="text-muted">분석 가능한 그래프가 없습니다.</p>';
  }
  // ⭐️ 삭제: 아래 타임테이블 관련 로직은 analysis-view와 관련 없으므로 삭제합니다.
}

// --- `dashboard.html` 용 함수들 ---
document.addEventListener("DOMContentLoaded", function () {
  loadPartDistributionChart();
  loadFailureRankingChart();
  loadFailureHeatmapChart();
  loadInstallationTrendChart();
  loadFailureLifespanRatioChart();
  loadFailureRateTrendChart();
});

async function fetchData(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return await response.json();
}

function loadPartDistributionChart() {
  fetchData("/api/part_distribution").then((data) => {
    const ctx = document
      .getElementById("partDistributionChart")
      .getContext("2d");
    new Chart(ctx, {
      type: "pie",
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.data,
            backgroundColor: [
              "rgba(255, 99, 132, 0.8)",
              "rgba(54, 162, 235, 0.8)",
              "rgba(255, 206, 86, 0.8)",
              "rgba(75, 192, 192, 0.8)",
              "rgba(153, 102, 255, 0.8)",
              "rgba(255, 159, 64, 0.8)",
            ],
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
      },
    });
  });
}

function loadFailureRankingChart() {
  fetchData("/api/failure_ranking").then((data) => {
    const ctx = document.getElementById("failureRankingChart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "고장 횟수",
            data: data.data,
            backgroundColor: "rgba(255, 99, 132, 0.8)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            precision: 0,
          },
        },
      },
    });
  });
}

function loadInstallationTrendChart() {
  fetchData("/api/installation_trend").then((data) => {
    const ctx = document
      .getElementById("installationTrendChart")
      .getContext("2d");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "설치 건수",
            data: data.data,
            borderColor: "rgba(54, 162, 235, 0.8)",
            borderWidth: 2,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            precision: 0,
          },
        },
      },
    });
  });
}

function loadFailureLifespanRatioChart() {
  fetchData("/api/failure_lifespan_ratio").then((data) => {
    const ctx = document.getElementById("timeToFailureChart").getContext("2d"); // canvas ID는 그대로 사용
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "고장 수명 비율 (%)",
            data: data.data,
            backgroundColor: "rgba(153, 102, 255, 0.8)",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y", // 가로 막대 그래프
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) =>
                `${context.dataset.label}: ${context.raw.toFixed(2)}%`,
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "고장 수명 비율 (%)" },
            beginAtZero: true,
          },
          y: {
            title: { display: true, text: "부품 ID" },
          },
        },
      },
    });
  });
}

function loadFailureHeatmapChart() {
  fetchData("/api/failure_heatmap").then((data) => {
    const ctx = document
      .getElementById("lifespanDistributionChart")
      .getContext("2d"); // canvas ID는 그대로 사용
    new Chart(ctx, {
      type: "matrix",
      data: {
        datasets: [
          {
            label: "월별 고장 횟수",
            data: data.dataset,
            backgroundColor: (ctx) => {
              const value = ctx.raw?.v || 0;
              const alpha = value > 0 ? 0.2 + value / 5 : 0.1; // 고장 횟수에 따라 투명도 조절
              return `rgba(255, 99, 132, ${alpha})`;
            },
            borderColor: "rgba(200, 200, 200, 0.5)",
            borderWidth: 1,
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
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => items[0].raw.y,
              label: (item) => `날짜: ${item.raw.x}\n고장: ${item.raw.v}회`,
            },
          },
        },
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
    const ctx = document
      .getElementById("failureRateTrendChart")
      .getContext("2d");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "월별 고장 건수",
            data: data.data,
            borderColor: "rgba(255, 99, 132, 0.8)",
            borderWidth: 2,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            precision: 0,
          },
        },
      },
    });
  });
}

// ⭐️ 삭제: 아래 함수들은 simulator.html에만 필요한 기능이므로 공용 스크립트에서 삭제합니다.
// function renderTimeTable(ts) { ... }
// function drawTimeSeriesChart(ts, targetPct = 20, tbmTotal = 0) { ... }
// function highlightTS(idx) { ... }
// document.getElementById('download-csv')?.addEventListener('click', () => { ... });
