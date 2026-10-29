const productoId = document.currentScript.dataset.productoId;
const esConjunto = document.currentScript.dataset.tipo === 'conjunto';

let selectedColor = null;
let selectedTalle = null;
let tallesData = [];
let selectedInferior = null;
let stockSuperior = 0;
let stockInferior = 0;
let currentImgIndex = 0;

function setImg(url, el){
  document.getElementById('img').src = url;
  document.querySelectorAll('.miniaturas img').forEach(i => i.classList.remove('activa'));
  if (el) {
    el.classList.add('activa');
    if (el.dataset.index !== undefined) currentImgIndex = parseInt(el.dataset.index);
  }
}

function moverImg(delta){
  const miniaturas = document.querySelectorAll('.miniaturas img');
  if (!miniaturas.length) return;
  currentImgIndex = (currentImgIndex + delta + miniaturas.length) % miniaturas.length;
  const el = miniaturas[currentImgIndex];
  setImg(el.src, el);
}

function cambiarCantidad(delta){
  const input = document.getElementById('cantidad');
  const limit = esConjunto ? Math.min(99, stockSuperior || 99, stockInferior || 99) :
    (selectedTalle ? Math.min(99, Number(document.querySelector('#tallesContainer .talle-btn.activo')?.dataset.stock || 99)) : 99);
  const nueva = Math.min(Math.max(1, parseInt(input.value) + delta), limit);
  input.value = nueva;
  actualizarHrefCarrito();
}

function actualizarHrefCarrito(){
  const cantidad = document.getElementById('cantidad').value;
  const addBtn = document.getElementById('addBtn');
  const addBtnSimple = document.getElementById('addBtnSimple');
  if (addBtn && !addBtn.classList.contains('disabled') && selectedColor && selectedTalle) {
    addBtn.href = `/tienda/agregar/${productoId}/?color=${selectedColor}&talle=${selectedTalle}${esConjunto ? `&talle_inferior=${selectedInferior}` : ''}&cantidad=${cantidad}`;
  }
  if (addBtnSimple) {
    addBtnSimple.href = `/tienda/agregar/${productoId}/?cantidad=${cantidad}`;
  }
}

function renderTalles(){
  const container = document.getElementById('tallesContainer');
  container.innerHTML = '';
  tallesData.forEach(encontrado => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'talle-btn';
    btn.textContent = encontrado.talle;
    btn.dataset.talle = encontrado.talle;
    if (encontrado.stock <= 0) {
      btn.classList.add('sin-stock');
      btn.disabled = true;
    } else {
      btn.dataset.id = encontrado.id;
      btn.dataset.stock = encontrado.stock;
      btn.onclick = () => setTalle(encontrado.id, encontrado.stock, btn);
    }
    container.appendChild(btn);
  });
}

function setColor(id, btn){
  selectedColor = id;
  selectedTalle = null;
  document.querySelectorAll('.cor-btn').forEach(b => b.classList.remove('activo'));
  btn.classList.add('activo');
  document.getElementById('msgColor').classList.remove('visible');
  document.getElementById('msgStock').classList.remove('visible');
  document.getElementById('msgPocoStock').textContent = '';
  document.getElementById('msgPocoStock').classList.remove('visible');
  document.getElementById('addBtn').classList.add('disabled');
  document.getElementById('addBtn').setAttribute('aria-disabled', 'true');
  document.getElementById('addBtn').setAttribute('tabindex', '-1');
  document.getElementById('addBtn').href = '#';

  const imgAsociada = document.querySelector(`.miniaturas img[data-color="${id}"]`);
  if (imgAsociada) setImg(imgAsociada.src, imgAsociada);

  fetch(`/tienda/talles/${id}/`).then(r => r.json()).then(data => {
    if (selectedColor !== id) return;
    tallesData = data.talles; renderTalles();
  });
}

function setTalle(id, stock, btn){
  selectedTalle = id;
  document.querySelectorAll('.talle-btn').forEach(b => b.classList.remove('activo'));
  btn.classList.add('activo');
  document.getElementById('cantidad').value = '1';
  document.getElementById('msgTalle').classList.remove('visible');
  document.getElementById('msgStock').classList.remove('visible');
  const msgPoco = document.getElementById('msgPocoStock');
  msgPoco.textContent = '';
  msgPoco.classList.remove('visible');
  if (stock <= 2) {
    msgPoco.textContent = stock === 1 ? '¡Última unidad disponible!' : `¡Quedan solo ${stock} unidades!`;
    msgPoco.classList.add('visible');
  }
  const addBtn = document.getElementById('addBtn');
  const cantidad = document.getElementById('cantidad').value;
  addBtn.href = `/tienda/agregar/${productoId}/?color=${selectedColor}&talle=${id}&cantidad=${cantidad}`;
  addBtn.classList.remove('disabled');
  addBtn.removeAttribute('aria-disabled');
  addBtn.removeAttribute('tabindex');
}

function renderTallesConjunto(containerId, data, side){
  const container = document.getElementById(containerId);
  container.replaceChildren();
  data.forEach(size => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'talle-btn';
    btn.textContent = size.talle;
    btn.disabled = size.stock <= 0;
    if (btn.disabled) btn.classList.add('sin-stock');
    btn.addEventListener('click', () => {
      container.querySelectorAll('.talle-btn').forEach(other => {other.classList.remove('activo');other.setAttribute('aria-pressed','false');});
      btn.classList.add('activo'); btn.setAttribute('aria-pressed','true');
      if (side === 'superior') {selectedTalle = size.id;stockSuperior = size.stock;}
      else {selectedInferior = size.id;stockInferior = size.stock;}
      document.getElementById('cantidad').value = '1';
      actualizarConjunto();
    });
    container.appendChild(btn);
  });
}

function setColorConjunto(id, btn){
  selectedColor = id; selectedTalle = null; selectedInferior = null;
  stockSuperior = 0; stockInferior = 0;
  document.querySelectorAll('.cor-btn').forEach(other => {other.classList.remove('activo');other.setAttribute('aria-pressed','false');});
  btn.classList.add('activo'); btn.setAttribute('aria-pressed','true');
  document.getElementById('tallesSuperior').replaceChildren();
  document.getElementById('tallesInferior').replaceChildren();
  actualizarConjunto();
  fetch(`/tienda/talles-conjunto/${productoId}/${id}/`).then(r => r.json()).then(data => {
    if (selectedColor !== id) return;
    renderTallesConjunto('tallesSuperior', data.superior, 'superior');
    renderTallesConjunto('tallesInferior', data.inferior, 'inferior');
  }).catch(() => {
    const message = document.getElementById('msgSet');
    message.textContent = 'No pudimos cargar los talles. Volvé a elegir el color.';
    message.classList.add('visible');
  });
  const img = document.querySelector(`.miniaturas img[data-color="${id}"]`);
  if (img) setImg(img.src, img);
}

function actualizarConjunto(){
  const enabled = selectedColor && selectedTalle && selectedInferior;
  const btn = document.getElementById('addBtn');
  btn.classList.toggle('disabled', !enabled);
  btn.setAttribute('aria-disabled', String(!enabled));
  btn.tabIndex = enabled ? 0 : -1;
  btn.href = enabled ? `/tienda/agregar/${productoId}/?color=${selectedColor}&talle=${selectedTalle}&talle_inferior=${selectedInferior}&cantidad=${document.getElementById('cantidad').value}` : '#';
  document.getElementById('msgSet').classList.toggle('visible', false);
}
