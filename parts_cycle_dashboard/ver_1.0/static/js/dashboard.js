document.addEventListener('DOMContentLoaded', function () {
    fetchAnalysisData();
});

async function fetchAnalysisData() {
    try {
        const response = await fetch('/api/analysis_results');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const results = await response.json();
        updateDashboard(results);
    } catch (error) {
        console.error("분석 데이터를 가져오는 데 실패했습니다:", error);
        const summarySection = document.getElementById('summary-section');
        summarySection.innerHTML = `<div class="alert alert-danger">데이터 분석 중 오류가 발생했습니다.</div>`;
    }
}

function updateDashboard(results) {
    const summarySection = document.getElementById('summary-section');
    summarySection.innerHTML = '';

    if (Object.keys(results).length === 0) {
        summarySection.innerHTML = `<div class="alert alert-info">분석할 데이터가 없습니다. 먼저 데이터를 추가해주세요.</div>`;
        return;
    }

    // 요약 테이블 생성 (기존과 동일)
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
        <tbody></tbody>
    `;
    const summaryTbody = summaryTable.querySelector('tbody');

    const chartTabs = document.getElementById('chart-tabs');
    const chartTabsContent = document.getElementById('chart-tabs-content');

    chartTabs.innerHTML = '';
    chartTabsContent.innerHTML = '';
    
    let isFirstTab = true;

    for (const partId in results) {
        const data = results[partId];
        
        // 요약 테이블 행 추가
        const row = summaryTbody.insertRow();
        row.innerHTML = `
            <td><strong>${partId}</strong></td>
            <td>${data.beta !== null ? data.beta : 'N/A'}</td>
            <td>${data.eta !== null ? data.eta.toLocaleString() : 'N/A'}</td>
            <td>${data.b10_life !== null ? data.b10_life.toLocaleString() : 'N/A'}</td>
            <td>${data.error ? `<span class="badge bg-warning text-dark">${data.error}</span>` : '<span class="badge bg-success">분석 완료</span>'}</td>
        `;

        // 플롯 데이터가 있을 경우에만 탭과 차트 생성
        if (data.plot_data) {
            const safePartId = partId.replace(/[^a-zA-Z0-9]/g, '');

            // 1. 탭 버튼 생성
            const tabItem = document.createElement('li');
            tabItem.className = 'nav-item';
            tabItem.innerHTML = `<button class="nav-link ${isFirstTab ? 'active' : ''}" id="tab-${safePartId}" data-bs-toggle="tab" data-bs-target="#pane-${safePartId}" type="button" role="tab" aria-controls="pane-${safePartId}" aria-selected="${isFirstTab}">${partId}</button>`;
            chartTabs.appendChild(tabItem);

            // 2. 탭 패널 생성
            const tabPane = document.createElement('div');
            tabPane.className = `tab-pane fade ${isFirstTab ? 'show active' : ''}`;
            tabPane.id = `pane-${safePartId}`;
            tabPane.setAttribute('role', 'tabpanel');

            // --- 코드 수정: 탭 패널 내부를 그리드로 나누어 차트와 테이블 배치 ---
            const contentRow = document.createElement('div');
            contentRow.className = 'row mt-3';

            // 왼쪽 컬럼 (차트)
            const chartCol = document.createElement('div');
            chartCol.className = 'col-md-8';
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
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

            // B10 수명 데이터를 표의 맨 위에 추가 (신뢰도 90% 시점)
            if (data.b10_life) {
                const b10Row = tableBody.insertRow();
                b10Row.innerHTML = `<td class="fw-bold">${Math.round(data.b10_life).toLocaleString()} (B10)</td><td class="fw-bold">90.00 %</td>`;
            }
            
            // 그래프 데이터에서 일부를 추출하여 표에 추가
            const plotX = data.plot_data.x;
            const plotY = data.plot_data.y;
            const pointsToShow = 6;
            const step = Math.floor(plotX.length / (pointsToShow + 1));

            for (let i = step; i < plotX.length; i += step) {
                if (plotX[i] > 0) {
                    const tr = tableBody.insertRow();
                    const time = Math.round(plotX[i]).toLocaleString();
                    const prob = (plotY[i] * 100).toFixed(2);
                    tr.innerHTML = `<td>${time}</td><td>${prob} %</td>`;
                }
            }
            tableCol.appendChild(dataTable);

            // 그리드 행에 컬럼들을 추가하고, 탭 패널에 최종적으로 추가
            contentRow.appendChild(chartCol);
            contentRow.appendChild(tableCol);
            tabPane.appendChild(contentRow);
            chartTabsContent.appendChild(tabPane);

            // 3. 차트 생성
            new Chart(canvas, {
                type: 'line',
                data: {
                    labels: data.plot_data.x,
                    datasets: [{
                        label: `생존 확률 (Survival Probability)`,
                        data: data.plot_data.y,
                        borderColor: 'rgb(75, 192, 192)',
                        tension: 0.1,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: { display: true, text: `${partId} 와이블 생존 곡선 (β=${data.beta}, η=${data.eta})`, font: { size: 16 } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) { label += ': '; }
                                    label += `시간: ${context.label}h, 확률: ${(context.raw * 100).toFixed(2)}%`;
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: { title: { display: true, text: '사용 시간 (Hours)' } },
                        y: { title: { display: true, text: '생존 확률' }, min: 0, max: 1.05 }
                    }
                }
            });
            
            isFirstTab = false;
        }
    }
    summarySection.appendChild(summaryTable);

    if (chartTabs.innerHTML === '') {
        chartTabs.innerHTML = '<li class="nav-item ps-3 text-muted">분석된 그래프가 없습니다.</li>';
    }
}