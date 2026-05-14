// Chart.js helper for SwasthyaSetu dashboards
function makeLineChart(canvasId, labels, data, title='Bookings') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.length ? labels : ['No data'],
      datasets: [{
        label: title,
        data: data.length ? data : [0],
        borderColor: '#0d6efd',
        backgroundColor: 'rgba(13,110,253,0.12)',
        borderWidth: 3,
        tension: 0.35,
        fill: true,
        pointBackgroundColor: '#0d6efd',
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
  });
}

function makeDoughnut(canvasId, labels, data, colors) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors || ['#0a7c6b','#0d6efd','#dc3545','#ffc107','#198754','#6f42c1'],
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: { legend: { position: 'bottom', labels: { padding: 14, font: { size: 12 } } } },
    }
  });
}

function makeBarChart(canvasId, labels, data, title='Hospitals') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels.length ? labels : ['No data'],
      datasets: [{
        label: title,
        data: data.length ? data : [0],
        backgroundColor: ['#0a7c6b','#0d6efd','#6f42c1','#fd7e14','#dc3545','#198754'],
        borderRadius: 8,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
  });
}
