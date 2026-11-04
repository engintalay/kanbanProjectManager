// Sprint report page: card table status filter + status/assignee charts.
// Data comes from JSON islands rendered by the view (status-chart, assignee-chart).

// Sprint kartı tablosunda duruma göre filtreleme
document.querySelectorAll('.card-filter-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.card-filter-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    var filter = btn.dataset.filter;
    document.querySelectorAll('#sprintCardTable tbody tr[data-status]').forEach(function (row) {
      row.style.display = (filter === 'all' || row.dataset.status === filter) ? '' : 'none';
    });
  });
});

// 1. Sprint Kolon Dağılımı
const rawStatus = JSON.parse(document.getElementById('status-chart').textContent);

const ctxStatus = document.getElementById('statusChart').getContext('2d');
new Chart(ctxStatus, {
  type: 'doughnut',
  data: {
    labels: rawStatus.map(s => s.name),
    datasets: [{
      data: rawStatus.map(s => s.count),
      backgroundColor: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899'],
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

// 2. Geliştirici İş Yükü ve Tamamlanma Grafiği
const rawAssignees = JSON.parse(document.getElementById('assignee-chart').textContent);

const ctxAssignee = document.getElementById('assigneeChart').getContext('2d');
new Chart(ctxAssignee, {
  type: 'bar',
  data: {
    labels: rawAssignees.map(a => a.name),
    datasets: [
      {
        label: 'Tamamlanan Zorluk',
        data: rawAssignees.map(a => a.completed),
        backgroundColor: '#10b981'
      },
      {
        label: 'Toplam Üstlenilen Zorluk',
        data: rawAssignees.map(a => a.total),
        backgroundColor: '#3b82f6'
      }
    ]
  },
  options: {
    responsive: true,
    scales: {
      x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
      y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' }, beginAtZero: true }
    },
    plugins: {
      legend: { position: 'bottom', labels: { color: '#94a3b8' } }
    }
  }
});
