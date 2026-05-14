// Sidebar toggle (desktop collapse + mobile slide-over)
document.addEventListener('DOMContentLoaded', function() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  const toggleBtn = document.getElementById('sidebarToggle');

  if (!sidebar || !toggleBtn) return;

  const isMobile = () => window.innerWidth <= 991;

  toggleBtn.addEventListener('click', () => {
    if (isMobile()) {
      sidebar.classList.toggle('show');
      backdrop && backdrop.classList.toggle('show');
    } else {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('sb-collapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
    }
  });

  if (backdrop) {
    backdrop.addEventListener('click', () => {
      sidebar.classList.remove('show');
      backdrop.classList.remove('show');
    });
  }

  // Restore collapsed state on desktop
  if (!isMobile() && localStorage.getItem('sb-collapsed') === '1') {
    sidebar.classList.add('collapsed');
  }

  // Close mobile sidebar on link click
  sidebar.querySelectorAll('.sidebar-nav a').forEach(a => {
    a.addEventListener('click', () => {
      if (isMobile()) {
        sidebar.classList.remove('show');
        backdrop && backdrop.classList.remove('show');
      }
    });
  });
});
