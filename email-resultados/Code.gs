/**
 * RGNERA — Envío de resultados de la calculadora de huella por correo.
 *
 * Recibe un POST desde rgnera.com/calculadora con el resultado del usuario,
 * guarda el lead en la hoja "Leads" y envía un correo personalizado.
 *
 * Instalación: ver INSTALAR.md (script vinculado a un Google Sheet).
 */

const HOJA_LEADS = 'Leads';
const REMITENTE = 'RGNERA';
const MAX_POR_DIA = 400; // margen bajo la cuota de Gmail Workspace

function doPost(e) {
  try {
    const datos = JSON.parse(e.postData.contents);
    const email = String(datos.email || '').trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return respuesta({ ok: false, error: 'correo inválido' });
    }
    if (MailApp.getRemainingDailyQuota() < (1500 - MAX_POR_DIA)) {
      registrarLead(datos, email, 'pendiente (cuota)');
      return respuesta({ ok: true, nota: 'registrado; correo pendiente' });
    }
    registrarLead(datos, email, 'enviado');
    enviarResultados(datos, email);
    return respuesta({ ok: true });
  } catch (err) {
    return respuesta({ ok: false, error: String(err) });
  }
}

function doGet() {
  return respuesta({ ok: true, servicio: 'rgnera-resultados', version: 1 });
}

function respuesta(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function registrarLead(datos, email, estado) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let hoja = ss.getSheetByName(HOJA_LEADS);
  if (!hoja) {
    hoja = ss.insertSheet(HOJA_LEADS);
    hoja.appendRow(['Fecha', 'Email', 'Quiere newsletter', 'Anual (t CO₂e)',
                    'Mensual (kg)', 'vs promedio nacional', 'Top rubros',
                    'Correo', 'Importado a Substack']);
    hoja.setFrozenRows(1);
  }
  hoja.appendRow([
    new Date(), email,
    datos.boletin ? 'SÍ' : 'no',
    datos.anual_t || '', datos.mensual_kg || '',
    formatoPct(datos.vs_promedio_pct),
    (datos.top || []).map(function (t) { return t.nombre + ' (' + t.kg + ' kg)'; }).join(', '),
    estado, ''
  ]);
}

function formatoPct(p) {
  if (p === undefined || p === null || p === '') return '';
  const n = Number(p);
  return (n > 0 ? '+' : '') + n + '%';
}

function enviarResultados(datos, email) {
  const asunto = '🌎 Tu huella de carbono: ' + datos.anual_t + ' toneladas de CO₂e al año';
  MailApp.sendEmail({
    to: email,
    subject: asunto,
    htmlBody: construirCorreo(datos),
    name: REMITENTE
  });
}

function construirCorreo(d) {
  const OLIVO = '#475323', TINTA = '#20261A', CREMA = '#F5F1E6',
        AMBAR = '#C58A2E', LINEA = '#E3DCCB', CARD = '#FFFDF7';

  const n = Number(d.vs_promedio_pct || 0);
  let comparacion;
  if (n > 10)       comparacion = 'Tu huella está <b>' + n + '% arriba</b> del promedio nacional — hay buenas oportunidades de bajarla (abajo te decimos dónde).';
  else if (n < -10) comparacion = '¡Bien! Tu huella está <b>' + Math.abs(n) + '% abajo</b> del promedio nacional. Aún así, siempre hay margen.';
  else              comparacion = 'Tu huella está <b>muy cerca del promedio nacional</b>. Con pequeños cambios puedes ponerte del lado verde.';

  const filasTop = (d.top || []).map(function (t, i) {
    return '<tr>' +
      '<td style="padding:10px 14px;border-bottom:1px solid ' + LINEA + ';color:' + TINTA + ';font-size:14px">' + (i + 1) + '. ' + t.nombre + '</td>' +
      '<td style="padding:10px 14px;border-bottom:1px solid ' + LINEA + ';color:' + OLIVO + ';font-weight:bold;text-align:right;font-size:14px">' + t.kg + ' kg/mes</td>' +
      '</tr>';
  }).join('');

  const filasConsejos = (d.consejos || []).map(function (c) {
    return '<div style="background:' + CARD + ';border:1px solid ' + LINEA + ';border-radius:10px;padding:14px 16px;margin:10px 0">' +
      '<div style="color:' + TINTA + ';font-size:14px;font-weight:bold">' + c.titulo + '</div>' +
      (c.ahorro ? '<div style="color:' + OLIVO + ';font-size:13px;margin-top:4px">Ahorro potencial: ~' + c.ahorro + ' kg CO₂e al mes</div>' : '') +
      '</div>';
  }).join('');

  const bloqueBoletin = d.boletin
    ? '<p style="color:#5c6553;font-size:13px;margin:6px 0 0">Marcaste que quieres el newsletter: pronto recibirás lo nuevo de RGNERA. 💚</p>'
    : '<p style="font-size:14px;margin:14px 0 0"><a href="https://rgnera.substack.com/subscribe" style="color:' + AMBAR + ';font-weight:bold">→ Suscríbete al newsletter de RGNERA</a> <span style="color:#5c6553">para recibir artículos como estos.</span></p>';

  return '' +
  '<div style="background:' + CREMA + ';padding:28px 12px;font-family:Georgia,serif">' +
    '<div style="max-width:560px;margin:0 auto">' +
      '<div style="background:' + OLIVO + ';border-radius:14px 14px 0 0;padding:22px;text-align:center">' +
        '<div style="color:' + CREMA + ';letter-spacing:6px;font-size:15px;font-weight:bold">R G N E R A</div>' +
      '</div>' +
      '<div style="background:#ffffff;border:1px solid ' + LINEA + ';border-top:none;border-radius:0 0 14px 14px;padding:26px 24px">' +

        '<h1 style="color:' + OLIVO + ';font-size:21px;margin:0 0 6px">Tus resultados 🌱</h1>' +
        '<p style="color:#5c6553;font-size:14px;margin:0 0 18px">Gracias por medir tu huella en la calculadora de RGNERA. Aquí está tu desglose:</p>' +

        '<div style="background:' + OLIVO + ';border-radius:12px;padding:20px;text-align:center;margin-bottom:8px">' +
          '<div style="color:' + CREMA + ';font-size:38px;font-weight:bold;line-height:1">' + d.anual_t + '</div>' +
          '<div style="color:#AEB98C;font-size:13px;margin-top:4px">toneladas de CO₂e al año (' + d.mensual_kg + ' kg al mes)</div>' +
        '</div>' +
        '<p style="color:' + TINTA + ';font-size:14px;margin:14px 0 20px">' + comparacion + '</p>' +

        '<h2 style="color:' + OLIVO + ';font-size:16px;margin:0 0 8px">Tus 3 rubros más pesados</h2>' +
        '<table style="width:100%;border-collapse:collapse;background:' + CARD + ';border:1px solid ' + LINEA + ';border-radius:10px">' + filasTop + '</table>' +

        (filasConsejos ? '<h2 style="color:' + OLIVO + ';font-size:16px;margin:22px 0 4px">Por dónde empezar</h2>' + filasConsejos : '') +

        '<div style="text-align:center;margin:24px 0 6px">' +
          '<a href="https://rgnera.com/calculadora/" style="background:' + AMBAR + ';color:#3d2907;text-decoration:none;font-weight:bold;font-size:14px;padding:12px 22px;border-radius:10px;display:inline-block">Volver a calcular</a>' +
          '&nbsp;&nbsp;' +
          '<a href="https://rgnera.com/articulos/" style="color:' + OLIVO + ';font-size:14px;font-weight:bold">Leer la biblioteca →</a>' +
        '</div>' +
        bloqueBoletin +

      '</div>' +
      '<p style="color:#9a927d;font-size:11px;text-align:center;margin:14px 0 0;line-height:1.5">' +
        'Recibes este correo porque pediste tus resultados en rgnera.com/calculadora.<br>' +
        'No te suscribimos a nada sin tu permiso. · © CAMVIO · RGNERA · Hecho con 💚 en México' +
      '</p>' +
    '</div>' +
  '</div>';
}

/** Prueba manual: Ejecutar > probarEnvio (usa tu propio correo). */
function probarEnvio() {
  const demo = {
    email: Session.getActiveUser().getEmail(),
    boletin: false,
    anual_t: '4.8',
    mensual_kg: '400',
    vs_promedio_pct: 12,
    top: [
      { nombre: 'Transporte', kg: 145 },
      { nombre: 'Alimentos', kg: 120 },
      { nombre: 'Electricidad', kg: 65 }
    ],
    consejos: [
      { titulo: 'Comparte auto o usa transporte público 2 días a la semana', ahorro: 35 },
      { titulo: 'Reduce carne roja a 2 veces por semana', ahorro: 28 }
    ]
  };
  registrarLead(demo, demo.email, 'prueba');
  enviarResultados(demo, demo.email);
}
