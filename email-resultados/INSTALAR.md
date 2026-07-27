# Instalar el envío de resultados por correo (5 minutos)

Mismo patrón que el bot de Pavorosso: un Apps Script pegado a un Google Sheet.
El Sheet es la base de datos de leads; el script manda el correo personalizado.

## Pasos (los haces tú porque piden autorizar tu cuenta)

1. Entra a **sheets.new** (con pablo@rgnera.com) y nombra el archivo
   **"RGNERA — Leads Calculadora"**.
2. Menú **Extensiones → Apps Script**. Borra lo que haya y pega TODO el
   contenido de `Code.gs`. Guarda (Ctrl+S).
3. (Opcional pero recomendado) En el editor: **Ejecutar → probarEnvio** →
   autoriza los permisos cuando lo pida → revisa que te llegue el correo de
   prueba a tu buzón y que aparezca la fila en la hoja "Leads".
4. **Implementar → Nueva implementación → ⚙️ Aplicación web**:
   - Descripción: `resultados calculadora`
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier persona**
   - Implementar → copia la **URL de la aplicación web** (termina en `/exec`).
5. Pásale esa URL a Claude → conecta la calculadora y publica.

## Qué guarda la hoja "Leads"

Fecha · Email · Quiere newsletter · Huella anual y mensual · vs promedio
nacional · Top rubros · estado del correo · columna "Importado a Substack"
(para marcar cuando pases los SÍ al newsletter).

## Ritual sugerido (1 vez al mes)

Filtra los "Quiere newsletter = SÍ" no importados → cópialos → Substack →
Suscriptores → Añadir → pega los correos (con la casilla de bienvenida
apagada si prefieres) → marca la columna como importados.

## Notas

- Cuota de correo: ~1,500/día con Workspace; el script se frena solo en 400
  para nunca toparte.
- Si cambias el texto del correo: edita `construirCorreo()` y vuelve a
  **Implementar → Administrar implementaciones → editar (lápiz) → Nueva versión**.
