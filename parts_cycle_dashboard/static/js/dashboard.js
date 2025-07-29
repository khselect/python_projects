document.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname; // 현재 페이지의 경로를 가져옵니다.

    // 메인 페이지 (/) 기능 실행
    if (path === '/') {
        if (document.getElementById('pm-watchlist-section')) {
            loadPmWatchlist();
        }
    }
    // 수명 분석 결과 페이지 (/analysis-view) 기능 실행
    else if (path === '/analysis-view') {
        if (document.getElementById('summary-section')) {
            fetchAnalysisData();
        }
    }
    // 종합 대시보드 페이지 (/dashboard) 기능 실행
    else if (path === '/dashboard') {
        if (document.getElementById('partDistributionChart')) {
            // Chart.js 플러그인이 필요할 경우 여기에 등록
            // Chart.register(ChartDataLabels);
            loadDashboardCharts();
        }
    }
});

// 대시보드 초기화 및 탭 이벤트 리스너 설정
function initializeDashboard() {
    // 필수 플러그인 등록
    if (typeof ChartDataLabels !== 'undefined') {
        Chart.register(ChartDataLabels);
    }

    const chartLoadStatus = {}; // 각 차트의 로딩 상태를 추적
    const tabButtons = document.querySelectorAll('#dashboard-tabs .nav-link');

    // 첫 번째 탭(활성화된 탭)의 차트를 즉시 로드
    const activeTab = document.querySelector('#dashboard-tabs .nav-link.active');
    if (activeTab) {
        loadChartForTab(activeTab.id, chartLoadStatus);
    }

    // 각 탭 버튼에 클릭 이벤트 리스너 추가
    tabButtons.forEach(button => {
        button.addEventListener('shown.bs.tab', function(event) {
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
        case 'dist-tab':
            loadPartDistributionChart();
            break;
        case 'rank-tab':
            loadFailureRankingChart();
            break;
        case 'heatmap-tab':
            loadFailureHeatmapChart();
            break;
        case 'install-tab':
            loadInstallationTrendChart();
            break;
        case 'ratio-tab':
            loadFailureLifespanRatioChart();
            break;
        case 'trend-tab':
            loadFailureRateTrendChart();
            break;
    }
    chartLoadStatus[tabId] = true; // 로드 완료 상태로 표시
}

// --- `index.html` 용 함수들 ---

// async function loadPmWatchlist() {
//     const watchlistSection = document.getElementById('pm-watchlist-section');
//     if (!watchlistSection) return;

//     try {
//         const response = await fetch('/api/pm_watchlist');
//         if (!response.ok) throw new Error(`서버 응답 오류: ${response.status}`);
        
//         const watchlist = await response.json();
//         if (watchlist.error) throw new Error(`API 오류: ${watchlist.error}`);

//         if (watchlist.length === 0) {
//             watchlistSection.innerHTML = '<p class="text-muted mb-0">현재 점검이 필요한 부품이 없습니다.</p>';
//             return;
//         }

//         const table = document.createElement('table');
//         table.className = 'table table-hover align-middle mb-0';
//         table.innerHTML = `
//             <thead>
//                 <tr>
//                     <th>부품 ID</th>
//                     <th>시리얼 번호</th>
//                     <th>현재 가동시간</th>
//                     <th>B10 수명</th>
//                     <th style="width: 25%;">위험도</th>
//                     <th>상태</th>
//                 </tr>
//             </thead>
//             <tbody></tbody>
//         `;
//         const tbody = table.querySelector('tbody');

//         watchlist.forEach(item => {
//             const statusColor = item.status === '위험' ? 'bg-danger' : 'bg-warning';
//             const row = tbody.insertRow();
//             row.innerHTML = `
//                 <td><strong>${item.part_id}</strong></td>
//                 <td>${item.serial_number || 'N/A'}</td>
//                 <td>${item.operating_hours.toLocaleString()} 시간</td>
//                 <td>${item.b10_life.toLocaleString()} 시간</td>
//                 <td>
//                     <div class="progress" style="height: 20px;">
//                         <div class="progress-bar ${statusColor}" role="progressbar" style="width: ${item.usage_ratio}%;" 
//                              aria-valuenow="${item.usage_ratio}" aria-valuemin="0" aria-valuemax="100">
//                              ${item.usage_ratio}%
//                         </div>
//                     </div>
//                 </td>
//                 <td><span class="badge ${statusColor}">${item.status}</span></td>
//             `;
//         });
//         watchlistSection.innerHTML = '';
//         watchlistSection.appendChild(table);

//     } catch (error) {
//         console.error("🚨 주의 목록 로딩 실패:", error);
//         watchlistSection.innerHTML = `<div class="alert alert-danger">주의 목록을 불러오는 중 오류가 발생했습니다.</div>`;
//     }
// }

async function fetchAnalysisData() {
    const summarySection = document.getElementById('summary-section');
    if (!summarySection) return;
    
    try {
        const response = await fetch('/api/analysis_results');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const results = await response.json();
        updateDashboard(results);
    } catch (error) {
        console.error("🚨 분석 결과 로딩 실패:", error);
        summarySection.innerHTML = `<div class="alert alert-danger">분석 결과를 불러오는 중 오류가 발생했습니다.</div>`;
    }
}

function updateDashboard(results) {
    const summarySection = document.getElementById('summary-section');
    const chartTabs = document.getElementById('chart-tabs');
    const chartTabsContent = document.getElementById('chart-tabs-content');

    if (!summarySection || !chartTabs || !chartTabsContent) return;
    
    summarySection.innerHTML = '';
    chartTabs.innerHTML = '';
    chartTabsContent.innerHTML = '';

    if (Object.keys(results).length === 0) {
        summarySection.innerHTML = `<div class="alert alert-info">분석할 데이터가 없습니다.</div>`;
        return;
    }

    const summaryTable = document.createElement('table');
    summaryTable.className = 'table table-bordered';
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
    const summaryTbody = summaryTable.querySelector('tbody');
    
    let isFirstTab = true;
    for (const partId in results) {
        const data = results[partId];
        const row = summaryTbody.insertRow();
        row.innerHTML = `
            <td><strong>${partId}</strong></td>
            <td>${data.beta !== null ? data.beta : 'N/A'}</td>
            <td>${data.eta !== null ? data.eta.toLocaleString() : 'N/A'}</td>
            <td>${data.b10_life !== null ? data.b10_life.toLocaleString() : 'N/A'}</td>
            <td>${data.error ? `<span class="badge bg-warning text-dark">${data.error}</span>` : '<span class="badge bg-success">분석 완료</span>'}</td>`;

        if (data.plot_data && data.plot_data.x && data.plot_data.y) {
            const safePartId = partId.replace(/[^a-zA-Z0-9]/g, '');
            const tabItem = document.createElement('li');
            tabItem.className = 'nav-item';
            tabItem.innerHTML = `<button class="nav-link ${isFirstTab ? 'active' : ''}" data-bs-toggle="tab" data-bs-target="#pane-${safePartId}" type="button">${partId}</button>`;
            chartTabs.appendChild(tabItem);
            
            const tabPane = document.createElement('div');
            tabPane.className = `tab-pane fade ${isFirstTab ? 'show active' : ''}`;
            tabPane.id = `pane-${safePartId}`;
            
            // ⭐️ 해결: 탭 내부를 그리드로 나누어 차트와 테이블을 배치합니다. ⭐️
            const contentRow = document.createElement('div');
            contentRow.className = 'row mt-2';

            // 왼쪽 컬럼 (차트)
            const chartCol = document.createElement('div');
            chartCol.className = 'col-md-8';
            const chartContainer = document.createElement('div');
            chartContainer.style.height = '350px';
            const canvas = document.createElement('canvas');
            chartContainer.appendChild(canvas);
            chartCol.appendChild(chartContainer);

            // 오른쪽 컬럼 (생존 확률 데이터 테이블)
            const tableCol = document.createElement('div');
            tableCol.className = 'col-md-4';
            const dataTable = document.createElement('table');
            dataTable.className = 'table table-sm table-hover table-bordered';
            dataTable.innerHTML = `
                <caption class="caption-top">주요 시간별 생존 확률</caption>
                <thead class="table-light">
                    <tr><th>시간 (h)</th><th>생존 확률 (%)</th></tr>
                </thead>
                <tbody></tbody>
            `;
            const tableBody = dataTable.querySelector('tbody');

            // B10 수명 데이터를 표의 맨 위에 추가
            if (data.b10_life) {
                const b10Row = tableBody.insertRow();
                b10Row.innerHTML = `<td class="fw-bold">${Math.round(data.b10_life).toLocaleString()} (B10)</td><td class="fw-bold">90.00 %</td>`;
            }
            
            // 그래프 데이터에서 일부를 추출하여 표에 추가
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
            tabPane.appendChild(contentRow); // contentRow를 tabPane에 추가
            chartTabsContent.appendChild(tabPane);

            new Chart(canvas, {
                type: 'line',
                data: {
                    labels: data.plot_data.x,
                    datasets: [{
                        label: '생존 확률',
                        data: data.plot_data.y,
                        borderColor: 'rgb(75, 192, 192)',
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
            isFirstTab = false;
        }
    }
    summarySection.appendChild(summaryTable);
    if (chartTabs.innerHTML === '') {
        chartTabsContent.innerHTML = '<p class="text-muted">분석 가능한 그래프가 없습니다.</p>';
    }
}

// --- `dashboard.html` 용 함수들 ---
document.addEventListener('DOMContentLoaded', function () {
    loadPartDistributionChart();
    loadFailureRankingChart();
    //loadLifespanDistributionChart();
    loadFailureHeatmapChart(); // 변경
    loadInstallationTrendChart();
    //loadTimeToFailureChart();
    loadFailureLifespanRatioChart(); // 변경
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
    fetchData('/api/part_distribution')
        .then(data => {
            const ctx = document.getElementById('partDistributionChart').getContext('2d');
            new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.data,
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.8)',
                            'rgba(54, 162, 235, 0.8)',
                            'rgba(255, 206, 86, 0.8)',
                            'rgba(75, 192, 192, 0.8)',
                            'rgba(153, 102, 255, 0.8)',
                            'rgba(255, 159, 64, 0.8)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        });
}

function loadFailureRankingChart() {
    fetchData('/api/failure_ranking')
        .then(data => {
            const ctx = document.getElementById('failureRankingChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: '고장 횟수',
                        data: data.data,
                        backgroundColor: 'rgba(255, 99, 132, 0.8)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            precision: 0
                        }
                    }
                }
            });
        });
}

// function loadLifespanDistributionChart() {
//     fetchData('/api/lifespan_distribution')
//         .then(data => {
//             const ctx = document.getElementById('lifespanDistributionChart').getContext('2d');
//             new Chart(ctx, {
//                 type: 'histogram',
//                 data: {
//                     datasets: [{
//                         label: '수명 (일)',
//                         data: data.data,
//                         backgroundColor: 'rgba(75, 192, 192, 0.8)',
//                         borderWidth: 1
//                     }]
//                 },
//                 options: {
//                     responsive: true,
//                     maintainAspectRatio: false,
//                     scales: {
//                         x: {
//                             title: {
//                                 display: true,
//                                 text: '수명 (일)'
//                             }
//                         },
//                         y: {
//                             title: {
//                                 display: true,
//                                 text: '빈도'
//                             },
//                             beginAtZero: true,
//                             precision: 0
//                         }
//                     },
//                     plugins: {
//                         legend: {
//                             display: false
//                         },
//                         tooltip: {
//                             callbacks: {
//                                 title: (items) => `수명: ${items.length > 0 ? items?.[0]?.label : 'N/A'} 일`,
//                                 label: (item) => `빈도: ${item.formattedValue}`
//                             }
//                         }
//                     }
//                 },
//                 plugins: {
//                     chartjsPluginHistogram: {}
//                 }
//             });
//         });
// }

function loadInstallationTrendChart() {
    fetchData('/api/installation_trend')
        .then(data => {
            const ctx = document.getElementById('installationTrendChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: '설치 건수',
                        data: data.data,
                        borderColor: 'rgba(54, 162, 235, 0.8)',
                        borderWidth: 2,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            precision: 0
                        }
                    }
                }
            });
        });
}

// function loadTimeToFailureChart() {
//     fetchData('/api/time_to_failure')
//         .then(data => {
//             const partLifespans = {};
//             data.forEach(item => {
//                 if (!partLifespans.hasOwnProperty(item.part_id)) {
//                     partLifespans [item.part_id] = [];
//                 }
//                 partLifespans [item.part_id].push(item.lifespan);
//             });

//             const labels = Object.keys(partLifespans);
//             const datasets = labels.map(partId => ({
//                 label: partId,
//                 data: partLifespans [partId],
//                 backgroundColor: `rgba(${Math.random() * 255}, ${Math.random() * 255}, ${Math.random() * 255}, 0.7)`,
//                 borderColor: 'rgba(0, 0, 0, 1)',
//                 borderWidth: 1,
//                 pointRadius: 5
//             }));

//             const ctx = document.getElementById('timeToFailureChart').getContext('2d');
//             new Chart(ctx, {
//                 type: 'scatter',
//                 data: { datasets },
//                 options: {
//                     responsive: true,
//                     maintainAspectRatio: false,
//                     scales: {
//                         x: {
//                             title: {
//                                 display: true,
//                                 text: '부품 ID'
//                             },
//                             type: 'category',
//                             labels: labels
//                         },
//                         y: {
//                             title: {
//                                 display: true,
//                                 text: '고장 수명 (일)'
//                             },
//                             beginAtZero: true
//                         }
//                     },
//                     plugins: {
//                         legend: {
//                             display: true
//                         },
//                         tooltip: {
//                             callbacks: {
//                                 title: (items) => items?.[0]?.dataset?.label || '',
//                                 label: (item) => `수명: ${item.raw.y} 일`
//                             }
//                         }
//                     }
//                 }
//             });
//         });
// }

// 고장 수명 비율 그래프 (기존 고장 시간 그래프 대체)
function loadFailureLifespanRatioChart() {
    fetchData('/api/failure_lifespan_ratio')
        .then(data => {
            const ctx = document.getElementById('timeToFailureChart').getContext('2d'); // canvas ID는 그대로 사용
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: '고장 수명 비율 (%)',
                        data: data.data,
                        backgroundColor: 'rgba(153, 102, 255, 0.8)',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y', // 가로 막대 그래프
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (context) => `${context.dataset.label}: ${context.raw.toFixed(2)}%`
                            }
                        }
                    },
                    scales: {
                        x: {
                            title: { display: true, text: '고장 수명 비율 (%)' },
                            beginAtZero: true
                        },
                        y: {
                            title: { display: true, text: '부품 ID' }
                        }
                    }
                }
            });
        });
}

// 고장 히트맵 (기존 수명 분포 그래프 대체)
function loadFailureHeatmapChart() {
    fetchData('/api/failure_heatmap')
        .then(data => {
            const ctx = document.getElementById('lifespanDistributionChart').getContext('2d'); // canvas ID는 그대로 사용
            new Chart(ctx, {
                type: 'matrix',
                data: {
                    datasets: [{
                        label: '월별 고장 횟수',
                        data: data.dataset,
                        backgroundColor: (ctx) => {
                            const value = ctx.raw?.v || 0;
                            const alpha = value > 0 ? 0.2 + value / 5 : 0.1; // 고장 횟수에 따라 투명도 조절
                            return `rgba(255, 99, 132, ${alpha})`;
                        },
                        borderColor: 'rgba(200, 200, 200, 0.5)',
                        borderWidth: 1,
                        width: ({chart}) => (chart.chartArea || {}).width / data.x_labels.length - 1,
                        height: ({chart}) => (chart.chartArea || {}).height / data.y_labels.length - 1,
                    }]
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
                            }
                        }
                    },
                    scales: {
                        x: { type: 'category', labels: data.x_labels, grid: { display: false } },
                        y: { type: 'category', labels: data.y_labels, grid: { display: false }, offset: true }
                    }
                }
            });
        });
}

function loadFailureRateTrendChart() {
    fetchData('/api/failure_rate_trend')
        .then(data => {
            const ctx = document.getElementById('failureRateTrendChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: '월별 고장 건수',
                        data: data.data,
                        borderColor: 'rgba(255, 99, 132, 0.8)',
                        borderWidth: 2,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            precision: 0
                        }
                    }
                }
            });
        });
}