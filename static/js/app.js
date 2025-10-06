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

  const media = window.matchMedia('(max-width: 1024px)');
  const applySidebarState = () => {
    if (media.matches) {
      document.body.classList.add('sidebar-hidden');
      document.body.classList.remove('sidebar-collapsed');
    } else {
      document.body.classList.remove('sidebar-hidden');
    }
  };

  applySidebarState();
  if (media.addEventListener) {
    media.addEventListener('change', applySidebarState);
  } else if (media.addListener) {
    media.addListener(applySidebarState);
  }

  document.querySelectorAll('[data-toggle-sidebar]').forEach((button) => {
    button.addEventListener('click', () => {
      if (media.matches) {
        document.body.classList.toggle('sidebar-hidden');
      } else {
        document.body.classList.toggle('sidebar-collapsed');
      }
    });
  });

  document.querySelectorAll('.sidebar nav a').forEach((link) => {
    link.addEventListener('click', () => {
      if (media.matches) {
        document.body.classList.add('sidebar-hidden');
      }
    });
  });
})();
