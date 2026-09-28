// Ejecuta el JavaScript servido por Flask con cámara, vídeo y red simulados.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync(0, 'utf8');
const eventos = {};
const mensajes = [];
const dibujos = [];
let vertical = false;
let httpOk = true;
let peticiones = 0;
let calidad;
let reloj = 0;
const temporizadores = new Map();
let siguienteTimer = 0;
const elementos = {
  cam: {videoWidth: 1280, videoHeight: 720, readyState: 2, currentTime: 0,
    addEventListener: (nombre, fn) => { eventos[nombre] = fn; }},
  lienzo: {width: 0, height: 0, getContext: () => ({drawImage: (...args) => dibujos.push(args)}),
    toBlob: (fn, tipo, valor) => { calidad = valor; assert.equal(tipo, 'image/jpeg'); fn({jpeg: true}); }},
  estado: {set textContent(valor) { mensajes.push(valor); }, className: ''},
  detalle: {textContent: ''},
  resolucion: {value: '', addEventListener: (nombre, fn) => { eventos[nombre] = fn; }},
  reconectar: {addEventListener: (nombre, fn) => { eventos.reconectar = fn; }}
};
const cambios = [];
const pista = {readyState: 'live', applyConstraints: async opciones => { cambios.push(opciones); }};
const contexto = vm.createContext({
  document: {hidden: false, getElementById: id => elementos[id],
    addEventListener: (nombre, fn) => { eventos[nombre] = fn; }},
  window: {matchMedia: () => ({matches: vertical}), addEventListener: (nombre, fn) => { eventos[nombre] = fn; }},
  // El arranque queda pendiente: cada prueba controla cuándo simular el vídeo.
  navigator: {mediaDevices: {getUserMedia: () => new Promise(() => {})}},
  setTimeout: (fn, ms) => {
    const id = ++siguienteTimer;
    temporizadores.set(id, {fn, ms});
    if (ms < 2000) queueMicrotask(() => {
      if (temporizadores.delete(id)) { reloj += ms; fn(); }
    });
    return id;
  },
  clearTimeout: id => temporizadores.delete(id), AbortController, console,
  performance: {now: () => reloj},
  fetch: async (url, opciones) => {
    peticiones++;
    assert.equal(url, '/subir');
    assert.equal(opciones.method, 'POST');
    pista.readyState = 'ended';
    return {ok: httpOk};
  }, pistaPrueba: pista
});
vm.runInContext(script, contexto);
const ejecutar = texto => vm.runInContext(texto, contexto);

(async () => {
  assert.equal(elementos.resolucion.value, '1280x720');
  assert.equal(ejecutar('restricciones().width.ideal'), 1280);
  vertical = true;
  assert.equal(ejecutar('restricciones().width.ideal'), 720);
  assert.equal(ejecutar('restricciones().height.ideal'), 1280);
  elementos.resolucion.value = '1920x1080';
  assert.equal(ejecutar('restricciones().height.ideal'), 1920);
  ejecutar('pista = pistaPrueba');
  await eventos.change();
  assert.equal(cambios[0].width.ideal, 1080);

  elementos.cam.videoWidth = 1080;
  elementos.cam.videoHeight = 1920;
  eventos.resize();
  assert.equal(elementos.lienzo.width, 1080);
  assert.equal(elementos.lienzo.height, 1920);
  vertical = false;
  elementos.cam.videoWidth = 1920;
  elementos.cam.videoHeight = 1080;
  eventos.orientationchange();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(cambios.at(-1).width.ideal, 1920);
  eventos.resize();
  assert.equal(elementos.lienzo.width, 1920);
  assert.equal(elementos.lienzo.height, 1080);

  // Safari entrega lo disponible, incluso si es menor que lo solicitado.
  elementos.cam.videoWidth = 640;
  elementos.cam.videoHeight = 480;
  pista.applyConstraints = async () => { throw new Error('No compatible'); };
  await eventos.change();
  assert.equal(elementos.lienzo.width, 640);
  assert.match(elementos.detalle.textContent, /No se pudo aplicar/);
  assert.equal(elementos.cam.videoWidth, 640);
  await ejecutar('enviar()');
  assert.equal(peticiones, 1);
  assert.deepEqual(dibujos[0].slice(1), [0, 0, 640, 480]);
  assert.equal(calidad, .85);
  assert(mensajes.some(m => m.includes('Transmitiendo al PC')));

  pista.readyState = 'live';
  httpOk = false;
  await ejecutar('enviar()');
  assert.equal(peticiones, 2);
  assert(mensajes.some(m => m.includes('Reintentando')));

  // Un toBlob que nunca invoca su callback debe salir por timeout.
  pista.readyState = 'live';
  elementos.lienzo.toBlob = () => {};
  const bloqueado = ejecutar('enviar()');
  const comprobacion = assert.rejects(bloqueado, /captura de imagen no responde/);
  const timerBlob = [...temporizadores.values()].find(t => t.ms === 3000);
  assert(timerBlob);
  timerBlob.fn();
  await comprobacion;

  // readyState bajo permanente también necesita recuperación.
  elementos.cam.readyState = 1;
  await assert.rejects(ejecutar('enviar()'), /dejó de avanzar/);

  // No declarar vídeo vivo si currentTime permanece congelado.
  elementos.cam.readyState = 2;
  elementos.lienzo.toBlob = fn => fn({jpeg: true});
  contexto.fetch = async () => { reloj += 7000; return {ok: true}; };
  await assert.rejects(ejecutar('enviar()'), /dejó de avanzar/);

  let detenida = 0;
  elementos.cam.srcObject = {getTracks: () => [{stop: () => detenida++}]};
  contexto.document.hidden = true;
  eventos.visibilitychange();
  assert.equal(detenida, 1);
  assert.equal(elementos.cam.srcObject, null);

  // El bloqueo de pantalla se vuelve a solicitar después de perderlo.
  contexto.document.hidden = false;
  let solicitudesBloqueo = 0;
  let liberar;
  contexto.navigator.wakeLock = {request: async () => {
    solicitudesBloqueo++;
    return {addEventListener: (nombre, fn) => { liberar = fn; }};
  }};
  await ejecutar('mantenerPantalla()');
  await ejecutar('mantenerPantalla()');
  assert.equal(solicitudesBloqueo, 1);
  liberar();
  await ejecutar('mantenerPantalla()');
  assert.equal(solicitudesBloqueo, 2);

  // El supervisor abre otra cámara cuando una pista termina, sin recargar.
  let aperturas = 0;
  let cierres = 0;
  elementos.cam.play = async () => {};
  contexto.navigator.mediaDevices.getUserMedia = async () => {
    aperturas++;
    const track = {readyState: 'ended', applyConstraints: async () => {}, stop: () => cierres++};
    if (aperturas === 2) contexto.document.hidden = true;
    return {getVideoTracks: () => [track], getTracks: () => [track]};
  };
  const programar = contexto.setTimeout;
  contexto.setTimeout = (fn, ms) => ms === 500 ? 0 : programar(fn, ms);
  ejecutar('iniciar()');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(aperturas, 2);
  assert.equal(cierres, 2);
  console.log('HD, orientacion, cambio de resolucion, fallback y envio verificados');
})().catch(error => { console.error(error); process.exitCode = 1; });
