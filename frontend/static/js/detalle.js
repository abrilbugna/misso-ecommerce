const productoId = document.currentScript.dataset.productoId;

let selectedColor = null;
let selectedTalle = null;
let tallesData = [];
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
  const nueva = Math.max(1, parseInt(input.value) + delta);
  input.value = nueva;
  actualizarHrefCarrito();
}

function actualizarHrefCarrito(){
  const cantidad = document.getElementById('cantidad').value;
  const addBtn = document.getElementById('addBtn');
  const addBtnSimple = document.getElementById('addBtnSimple');
  if (addBtn && !addBtn.classList.contains('disabled') && selectedColor && selectedTalle) {
    addBtn.href = `/tienda/agregar/${productoId}/?color=${selectedColor}&talle=${selectedTalle}&cantidad=${cantidad}`;
  }
  if (addBtnSimple) {
    addBtnSimple.href = `/tienda/agregar/${productoId}/?cantidad=${cantidad}`;
  }
}

function renderTalles(){
  const container = document.getElementById('tallesContainer');
  const tallesOrden = [85, 90, 95, 100];
  container.innerHTML = '';
  tallesOrden.forEach(nombre => {
    const btn = document.createElement('button');
    btn.className = 'talle-btn';
    btn.textContent = nombre;
    btn.dataset.talle = nombre;
    if (!selectedColor) { btn.disabled = true; container.appendChild(btn); return; }
    const encontrado = tallesData.find(t => String(t.talle) === String(nombre));
    if (!encontrado || encontrado.stock <= 0) {
      btn.classList.add('sin-stock');
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

  fetch(`/tienda/talles/${id}/`).then(r => r.json()).then(data => { tallesData = data.talles; renderTalles(); });
}

function setTalle(id, stock, btn){
  selectedTalle = id;
  document.querySelectorAll('.talle-btn').forEach(b => b.classList.remove('activo'));
  btn.classList.add('activo');
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
