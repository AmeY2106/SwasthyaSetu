// Animated counter for hero stats
document.addEventListener('DOMContentLoaded', function() {
  const counters = document.querySelectorAll('[data-counter]');
  counters.forEach(el => {
    const target = parseInt(el.dataset.counter, 10) || 0;
    let current = 0;
    const duration = 1500;
    const stepTime = 30;
    const steps = Math.max(1, Math.floor(duration / stepTime));
    const inc = target / steps;
    const tick = () => {
      current += inc;
      if (current >= target) { el.textContent = target; return; }
      el.textContent = Math.floor(current);
      setTimeout(tick, stepTime);
    };
    tick();
  });

  // Auto-dismiss flash messages
  setTimeout(() => {
    document.querySelectorAll('.alert.auto-dismiss').forEach(a => {
      a.style.transition = 'opacity .5s';
      a.style.opacity = '0';
      setTimeout(() => a.remove(), 500);
    });
  }, 4000);
});

// Helper to format datetime-local default to now
function nowDatetimeLocal(offsetMinutes = 0) {
  const d = new Date(Date.now() + offsetMinutes * 60000);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
