(() => {
  'use strict';
  const editor = document.querySelector('[data-product-editor]');
  if (!editor) return;
  const lowStock = Number(editor.dataset.lowStock);
  const direct = (set, selector) => Array.from(set.children).find(node => node.matches(selector));
  const totalInput = set => document.getElementById(`id_${set.dataset.prefix}-TOTAL_FORMS`);
  const rows = set => direct(set, '[data-rows]');
  const objectURLs = new Set();

  function syncColors() {
    const choices = Array.from(editor.querySelectorAll('[data-color-block]')).map(block => {
      const input = block.querySelector('input[name$="-nombre"]');
      return [input.name.slice(0, -7), input.value.trim()];
    }).filter(([, name]) => name);
    editor.querySelectorAll('select[name$="-color_ref"]').forEach(select => {
      const previous = select.value;
      select.replaceChildren(new Option('General · todos los colores', ''), ...choices.map(([key, name]) => new Option(name, key)));
      if (choices.some(([key]) => key === previous)) select.value = previous;
    });
  }

  function stockLabels() {
    editor.querySelectorAll('.panel-size-row').forEach(row => {
      const input = row.querySelector('input[name$="-stock"]');
      const label = row.querySelector('[data-stock-label]');
      const value = Number(input.value);
      label.textContent = input.value === '' ? '' : value < 0 ? 'Revisá el stock' : value === 0 ? 'Sin stock' : value <= lowStock ? 'Stock bajo' : 'Disponible';
    });
  }

  function replacePrefix(root, oldPrefix, newPrefix) {
    const replace = value => value.split(oldPrefix).join(newPrefix);
    [root, ...root.querySelectorAll('*')].forEach(node => {
      for (const attribute of Array.from(node.attributes || [])) {
        if (attribute.value.includes(oldPrefix)) node.setAttribute(attribute.name, replace(attribute.value));
      }
      if (node instanceof HTMLTemplateElement) node.innerHTML = replace(node.innerHTML);
    });
  }

  editor.addEventListener('click', event => {
    const add = event.target.closest('[data-add]');
    if (add) {
      const set = add.closest('[data-formset]');
      const total = totalInput(set);
      if (Number(total.value) >= Number(set.dataset.max)) {
        window.alert('Alcanzaste el máximo de filas para esta sección.');
        return;
      }
      const prefix = set.dataset.prefix;
      const fragment = direct(set, 'template[data-empty]').content.cloneNode(true);
      const row = fragment.firstElementChild;
      replacePrefix(row, `${prefix}-__prefix__`, `${prefix}-${total.value}`);
      rows(set).append(fragment);
      total.value = Number(total.value) + 1;
      syncColors();
      stockLabels();
      row.querySelector('input:not([type=hidden]), select')?.focus();
    }
    const discard = event.target.closest('[data-discard-row]');
    if (discard) {
      const row = discard.closest('[data-form-row]');
      const set = row.parentElement.closest('[data-formset]');
      const initial = document.getElementById(`id_${set.dataset.prefix}-INITIAL_FORMS`);
      const index = Array.from(rows(set).children).indexOf(row);
      // This control only removes unsaved additions; persisted records have no such action.
      if (index < Number(initial.value)) return;
      if (set.dataset.prefix === 'colors') {
        editor.querySelectorAll('select[name$="-color_ref"]').forEach(select => {
          if (select.value === `colors-${index}`) select.value = '';
        });
      }
      row.remove();
      Array.from(rows(set).children).forEach((child, newIndex) => {
        if (newIndex < index) return;
        const oldPrefix = `${set.dataset.prefix}-${newIndex + 1}`;
        const newPrefix = `${set.dataset.prefix}-${newIndex}`;
        editor.querySelectorAll('select[name$="-color_ref"] option').forEach(option => {
          if (option.value === oldPrefix) option.value = newPrefix;
        });
        replacePrefix(child, `${oldPrefix}-`, `${newPrefix}-`);
      });
      totalInput(set).value = Number(totalInput(set).value) - 1;
      syncColors();
    }
  });

  editor.addEventListener('input', event => {
    if (event.target.name?.endsWith('-nombre')) syncColors();
    if (event.target.name?.endsWith('-stock')) stockLabels();
  });
  editor.addEventListener('change', event => {
    const input = event.target;
    if (!input.matches('[data-preview]') || !input.files[0]) return;
    const file = input.files[0];
    if (!file.type.startsWith(`${input.dataset.preview}/`)) return;
    const box = input.closest('[data-form-row]').querySelector('[data-preview-container]');
    const preview = document.createElement(input.dataset.preview === 'image' ? 'img' : 'video');
    const url = URL.createObjectURL(file);
    objectURLs.add(url);
    preview.src = url;
    if (preview.tagName === 'IMG') preview.alt = 'Vista previa del archivo seleccionado';
    else preview.controls = true;
    box.replaceChildren(preview);
  });
  editor.addEventListener('submit', event => {
    const deleted = editor.querySelector('input[name$="-DELETE"]:checked');
    const confirmation = editor.querySelector('[name="confirm_delete"]');
    if (deleted && !confirmation.checked) {
      event.preventDefault();
      confirmation.focus();
      confirmation.setCustomValidity('Confirmá la eliminación de los archivos marcados.');
      confirmation.reportValidity();
    }
  });
  editor.querySelector('[name="confirm_delete"]').addEventListener('change', event => event.target.setCustomValidity(''));
  window.addEventListener('pagehide', () => objectURLs.forEach(url => URL.revokeObjectURL(url)));
  syncColors();
  stockLabels();
})();
