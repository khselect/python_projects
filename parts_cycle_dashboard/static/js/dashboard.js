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
    summarySection.innerHTML = ''; // 요약 섹션 초기화

    if (Object.keys(results).length === 0) {
        summarySection.innerHTML = `<div class="alert alert-info">분석할 데이터가 없습니다. 먼저 데이터를 추가해주세요.</div>`;
        return;
    }

    // --- 요약 테이블 생성 (기존과 동일) ---
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

    // === 코드 수정 부분: 차트 섹션을 탭으로 만드는 로직 ===
    const chartTabs = document.getElementById('chart-tabs');
    const chartTabsContent = document.getElementById('chart-tabs-content');

    // 이전 탭과 내용 초기화
    chartTabs.innerHTML = '';
    chartTabsContent.innerHTML = '';
    
    let isFirstTab = true; // 첫 번째 탭을 활성화하기 위한 플래그

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

        // 분석 결과에 플롯 데이터가 있을 경우에만 탭과 차트를 생성
        if (data.plot_data) {
            const safePartId = partId.replace(/[^a-zA-Z0-9]/g, ''); // HTML id로 사용하기 안전한 문자열 생성

            // 1. 탭 버튼 생성
            const tabItem = document.createElement('li');
            tabItem.className = 'nav-item';
            tabItem.innerHTML = `
                <button class="nav-link ${isFirstTab ? 'active' : ''}" id="tab-${safePartId}" data-bs-toggle="tab" data-bs-target="#pane-${safePartId}" type="button" role="tab" aria-controls="pane-${safePartId}" aria-selected="${isFirstTab}">
                    ${partId}
                </button>
            `;
            chartTabs.appendChild(tabItem);

            // 2. 탭 패널(차트가 들어갈 공간) 생성
            const tabPane = document.createElement('div');
            tabPane.className = `tab-pane fade ${isFirstTab ? 'show active' : ''}`;
            tabPane.id = `pane-${safePartId}`;
            tabPane.setAttribute('role', 'tabpanel');
            tabPane.setAttribute('aria-labelledby', `tab-${safePartId}`);
            
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
            const canvas = document.createElement('canvas');
            chartContainer.appendChild(canvas);
            tabPane.appendChild(chartContainer);
            chartTabsContent.appendChild(tabPane);

            // 3. 탭 패널 내부에 차트 생성
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
            
            isFirstTab = false; // 다음 탭부터는 active가 되지 않도록 플래그 변경
        }
    }

    // 요약 테이블을 섹션에 추가
    summarySection.appendChild(summaryTable);

    // 생성된 차트가 없을 경우 안내 메시지 표시
    if (chartTabs.innerHTML === '') {
        chartTabs.innerHTML = '<li class="nav-item ps-3 text-muted">분석된 그래프가 없습니다.</li>';
    }
}