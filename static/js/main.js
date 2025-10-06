document.addEventListener('DOMContentLoaded', () => {
  const toasts = Array.from(document.querySelectorAll('.toast'));
  toasts.forEach((toast) => {
    const closeButton = toast.querySelector('button[data-dismiss]');
    if (closeButton) {
      closeButton.addEventListener('click', () => toast.remove());
    }
    setTimeout(() => {
      toast.classList.add('toast--hide');
      setTimeout(() => toast.remove(), 220);
    }, 4200);
  });

  document.querySelectorAll('[data-table-search]').forEach((input) => {
    const targetSelector = input.getAttribute('data-table-target');
    const table = document.querySelector(targetSelector);
    if (!table) {
      return;
    }
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    input.addEventListener('input', (event) => {
      const term = event.target.value.toLowerCase();
      rows.forEach((row) => {
        row.style.display = row.innerText.toLowerCase().includes(term) ? '' : 'none';
      });
    });
  });

  document.querySelectorAll('[data-auto-submit]').forEach((element) => {
    element.addEventListener('change', () => {
      element.closest('form')?.submit();
    });
  });
  document.querySelectorAll('[data-invalid-message]').forEach((input) => {
    const message = input.getAttribute('data-invalid-message');
    const requiredMessage = input.getAttribute('data-required-message');
    input.addEventListener('invalid', () => {
      const value = input.value?.trim();
      if (!value && requiredMessage) {
        input.setCustomValidity(requiredMessage);
      } else if (message) {
        input.setCustomValidity(message);
      }
    });
    const clearValidity = () => input.setCustomValidity('');
    input.addEventListener('input', clearValidity);
    input.addEventListener('change', clearValidity);
  });

  document.querySelectorAll('[data-age-source]').forEach((source) => {
    const targetSelector = source.getAttribute('data-age-target');
    if (!targetSelector) {
      return;
    }
    const target = document.querySelector(targetSelector);
    if (!target) {
      return;
    }
    const atualizarIdade = () => {
      const temData = Boolean(source.value);
      if (!temData) {
        target.removeAttribute('readonly');
        target.classList.remove('input-readonly');
        target.value = target.value || '';
        target.setCustomValidity('');
        target.dispatchEvent(new Event('input', { bubbles: true }));
        return;
      }
      const nascimento = new Date(source.value);
      if (Number.isNaN(nascimento.getTime())) {
        target.removeAttribute('readonly');
        target.classList.remove('input-readonly');
        return;
      }
      const hoje = new Date();
      let idade = hoje.getFullYear() - nascimento.getFullYear();
      const mes = hoje.getMonth() - nascimento.getMonth();
      if (mes < 0 || (mes === 0 && hoje.getDate() < nascimento.getDate())) {
        idade -= 1;
      }
      target.value = idade >= 0 ? idade : '';
      target.setAttribute('readonly', 'readonly');
      target.classList.add('input-readonly');
      if (idade < 4 || idade > 18) {
        target.setCustomValidity('A idade calculada deve estar entre 4 e 18 anos.');
      } else {
        target.setCustomValidity('');
      }
      target.dispatchEvent(new Event('input', { bubbles: true }));
    };
    source.addEventListener('change', atualizarIdade);
    source.addEventListener('blur', atualizarIdade);
    if (target.value) {
      target.dispatchEvent(new Event('input', { bubbles: true }));
    }
    atualizarIdade();
  });

  document.querySelectorAll('[data-mask="phone"]').forEach((input) => {
    input.addEventListener('input', () => {
      input.value = input.value.replace(/[^0-9()+\s-]/g, '');
    });
  });

  document.querySelectorAll('[data-social-toggle]').forEach((checkbox) => {
    const targetSelector = checkbox.getAttribute('data-social-toggle');
    if (!targetSelector) {
      return;
    }
    const target = document.querySelector(targetSelector);
    if (!target) {
      return;
    }
    const toggleMensalidade = () => {
      if (checkbox.checked) {
        target.value = '0.00';
        target.setAttribute('readonly', 'readonly');
      } else {
        target.removeAttribute('readonly');
      }
    };
    checkbox.addEventListener('change', toggleMensalidade);
    toggleMensalidade();
  });
});
