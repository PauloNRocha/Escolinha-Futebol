(function(){
  const loader = document.querySelector('[data-loader]');
  window.addEventListener('load', () => {
    if (loader) {
      loader.classList.add('loader--hide');
      setTimeout(() => loader.remove(), 600);
    }
  });

  const activeLink = document.querySelector('.sidebar nav a.active');
  if (activeLink) {
    activeLink.classList.add('is-active');
  }

  const chartCanvas = document.querySelector('[data-chart]');
  if (chartCanvas && window.Chart && window.dashboardChartData) {
    new Chart(chartCanvas, {
      data: window.dashboardChartData
    });
  }

  document.querySelectorAll('[data-toggle-sidebar]').forEach((button) => {
    button.addEventListener('click', () => {
      document.body.classList.toggle('sidebar-collapsed');
    });
  });
})();
