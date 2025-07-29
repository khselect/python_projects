document.addEventListener('DOMContentLoaded', function () {
    loadBudgetForecast();
    loadReplacementCostChart();
    loadPriorityMaintenance(); // 함수 호출 변경

});

async function fetchData(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

// 예방 정비 우선순위 목록 생성 
function loadPriorityMaintenance() {
    const section = document.getElementById('pm-priority-section');
    fetchData('/api/priority_maintenance')
        .then(data => {
            if (data.error) throw new Error(data.error);
            if (data.length === 0) {
                section.innerHTML = '<p class="text-muted">현재 예방 정비가 권장되는 부품이 없습니다.</p>';
                return;
            }

            const table = document.createElement('table');
            table.className = 'table table-hover';
            table.innerHTML = `
                <thead class="table-light">
                    <tr>
                        <th>우선순위</th>
                        <th>부품 (S/N)</th>
                        <th>중요도</th>
                        <th>B10 수명 사용률</th>
                        <th>위험 점수</th>
                    </tr>
                </thead>
                <tbody></tbody>
            `;
            const tbody = table.querySelector('tbody');

            data.forEach((item, index) => {
                let priorityBadge = '';
                if (item.priority === '높음') priorityBadge = `<span class="badge bg-danger">${item.priority}</span>`;
                else if (item.priority === '중간') priorityBadge = `<span class="badge bg-warning text-dark">${item.priority}</span>`;
                else priorityBadge = `<span class="badge bg-secondary">${item.priority}</span>`;

                const row = tbody.insertRow();
                row.innerHTML = `
                    <td class="fw-bold">${index + 1}</td>
                    <td>${item.part_id}<br><small class="text-muted">${item.serial_number || ''}</small></td>
                    <td>${priorityBadge}</td>
                    <td>
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar bg-danger" role="progressbar" style="width: ${item.usage_ratio}%;">${item.usage_ratio}%</div>
                        </div>
                    </td>
                    <td class="fw-bold">${item.risk_score} 점</td>
                `;
            });

            section.innerHTML = '';
            section.appendChild(table);
        })
        .catch(error => {
            console.error("Error loading priority maintenance:", error);
            section.innerHTML = `<div class="alert alert-danger">우선순위 목록을 불러오는 중 오류가 발생했습니다.</div>`;
        });
}

// 고장 예측 기반 예산 계획
function loadBudgetForecast() {
    const section = document.getElementById('budget-forecast-section');
    fetchData('/api/cost/budget_forecast')
        .then(data => {
            if (data.error) {
                section.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류 발생: ${data.error}</div>`;
                return;
            }
            
            let totalCost = data.total_forecast_cost || 0;
            let detailsHtml = '';

            for (const [partId, values] of Object.entries(data.forecast_details)) {
                detailsHtml += `
                    <div class="col-md-3">
                        <div class="card text-center">
                            <div class="card-header">${partId}</div>
                            <div class="card-body">
                                <p class="card-text">예상 교체 수량: <strong>${values.count}</strong>개</p>
                                <p class="card-text">예상 비용: <strong>${values.total_cost.toLocaleString()}</strong>원</p>
                            </div>
                        </div>
                    </div>
                `;
            }

            if(detailsHtml === '') {
                detailsHtml = '<p class="text-muted">다음 분기 내 교체가 예상되는 부품이 없습니다.</p>';
            }

            section.innerHTML = `
                <div class="col-md-4">
                    <div class="card kpi-card">
                        <div class="card-body">
                            <h5 class="card-title text-muted">총 예상 교체 비용</h5>
                            <p class="kpi-value text-primary">${totalCost.toLocaleString()} 원</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-8">
                    <div class="row">
                        ${detailsHtml}
                    </div>
                </div>
            `;
        })
        .catch(error => {
            console.error("Error loading budget forecast:", error);
            section.innerHTML = `<div class="alert alert-danger">예측 데이터를 불러오는 중 오류가 발생했습니다.</div>`;
        });
}

// 부품별 총 교체 비용 (지난 1년)
function loadReplacementCostChart() {
    fetchData('/api/cost/replacement_last_year')
        .then(data => {
            const ctx = document.getElementById('replacementCostChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: '교체 비용 (원)',
                        data: data.data,
                        backgroundColor: 'rgba(255, 99, 132, 0.7)',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { callback: value => value.toLocaleString() + '원' } } }
                }
            });
        });
}

// 교체 우선순위 부품 추천 목록 생성 
function loadReplacementRecommendations() {
    const section = document.getElementById('replacement-recommendations-section');
    fetchData('/api/recommendations/replacement_priority')
        .then(data => {
            if (data.length === 0) {
                section.innerHTML = '<p class="text-muted">추천할 부품 데이터가 없습니다.</p>';
                return;
            }

            const table = document.createElement('table');
            table.className = 'table table-hover';
            table.innerHTML = `
                <thead class="table-light">
                    <tr>
                        <th>우선순위</th>
                        <th>부품 ID</th>
                        <th>중요도</th>
                        <th>고장 빈도</th>
                        <th>종합 점수</th>
                    </tr>
                </thead>
                <tbody></tbody>
            `;
            const tbody = table.querySelector('tbody');

            data.forEach((item, index) => {
                let priorityBadge = '';
                if (item.priority === '높음') {
                    priorityBadge = `<span class="badge bg-danger">${item.priority}</span>`;
                } else if (item.priority === '중간') {
                    priorityBadge = `<span class="badge bg-warning text-dark">${item.priority}</span>`;
                } else {
                    priorityBadge = `<span class="badge bg-secondary">${item.priority}</span>`;
                }

                const row = tbody.insertRow();
                row.innerHTML = `
                    <td class="fw-bold">${index + 1}</td>
                    <td>${item.part_id}</td>
                    <td>${priorityBadge}</td>
                    <td>${item.failure_count} 회</td>
                    <td class="fw-bold">${item.score} 점</td>
                `;
            });

            section.innerHTML = '';
            section.appendChild(table);
        })
        .catch(error => {
            console.error("Error loading replacement recommendations:", error);
            section.innerHTML = `<div class="alert alert-danger">추천 목록을 불러오는 중 오류가 발생했습니다.</div>`;
        });
}