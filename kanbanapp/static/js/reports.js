// Project reports page: status doughnut + sprint velocity charts.
// Data comes from JSON islands rendered by the view (status-chart, sprint-chart).
const rawStatus = JSON.parse(document.getElementById('status-chart').textContent);
const rawSprints = JSON.parse(document.getElementById('sprint-chart').textContent);

const ctxStatus = document.getElementById('statusChart').getContext('2d');
new Chart(ctxStatus, {
  type: 'doughnut',
  data: {
    labels: rawStatus.map(s => s.name),
    datasets: [{
      data: rawStatus.map(s => s.count),
      backgroundColor: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'],
      borderWidth: 1,
      borderColor: '#334155'
    }]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: 'bottom', labels: { color: '#94a3b8' } }
    }
  }
});

// 2. Sprint Velocity Chart (KPM-T3)
const ctxSprint = document.getElementById('sprintChart').getContext('2d');
new Chart(ctxSprint, {
  type: 'bar',
  data: {
    labels: rawSprints.map(s => s.name),
    datasets: [
      {
        label: 'Tamamlanan (Bitme)',
        data: rawSprints.map(s => s.completed),
        backgroundColor: '#10b981' // Yeşil
      },
      {
        label: 'Planlanan (Doluluk)',
        data: rawSprints.map(s => s.diff),
        backgroundColor: '#3b82f6' // Mavi (Asla yeşil değil)
      },
      {
        label: 'Hedef Kapasite',
        data: rawSprints.map(s => s.cap),
        backgroundColor: 'rgba(148, 163, 184, 0.4)'
      }
    ]
  },
  options: {
    responsive: true,
    scales: {
      x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
      y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
    },
    plugins: {
      legend: { position: 'bottom', labels: { color: '#94a3b8' } }
    }
  }
});
