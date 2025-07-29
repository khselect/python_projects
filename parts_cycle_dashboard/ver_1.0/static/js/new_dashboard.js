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