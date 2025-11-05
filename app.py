from flask import Flask, request, render_template_string, redirect, url_for, jsonify
import io
from contextlib import redirect_stdout
from threading import Thread, Lock
import time

# Reutilizamos la lógica existente sin levantar su servidor
import buscar_precios_web as precios
import leer_factura as facturas


app = Flask(__name__)


MENU_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Menú</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .card { border: 1px solid #ddd; padding: 16px; border-radius: 8px; margin: 12px 0; }
    a.button, button { display: inline-block; padding: 10px 16px; background: #1976d2; color: #fff; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; }
    a.button:hover, button:hover { background: #125a9e; }
  </style>
  </head>
  <body>
    <h2>Menú principal</h2>

    <div class="card">
      <h3>Buscar precios</h3>
      <p>Consultar precios guardados en la base de datos.</p>
      <a class="button" href="{{ url_for('precios_index') }}">Abrir búsqueda</a>
    </div>

    <div class="card">
      <h3>Leer facturas</h3>
      <p>Procesar facturas XML desde el correo IMAP y cargar precios.</p>
      <a class="button" href="{{ url_for('leer_facturas_page') }}">Abrir lector</a>
    </div>

    <div class="card">
      <h3>Calculadora de precio</h3>
      <p>Ingresa precio y margen para calcular el precio de venta.</p>
      <a class="button" href="{{ url_for('calculadora') }}">Abrir calculadora</a>
    </div>
  </body>
</html>
"""
CALCULADORA_HTML = """
<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <title>Calculadora de precio</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .container { max-width: 600px; margin: 0 auto; }
    .field { display: flex; flex-direction: column; margin-bottom: 12px; }
    label { font-weight: 600; margin-bottom: 6px; }
    input { padding: 8px; height: 36px; }
    .actions { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
    a.button, button.button { display: inline-block; padding: 8px 14px; background: #1976d2; color: #fff; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; }
    a.button:hover, button.button:hover { background: #125a9e; }
    a.button-secondary { background: #777; }
    a.button-secondary:hover { background: #5b5b5b; }
    .result { margin-top: 16px; background: #f7f7f7; padding: 12px; border-radius: 6px; }
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"actions\" style=\"margin-bottom:10px;\"><a class=\"button button-secondary\" href=\"{{ url_for('menu') }}\">← Volver</a></div>
    <h2>Calculadora de precio</h2>
    <form method=\"get\" action=\"{{ url_for('calculadora') }}\">
      <div class=\"field\">
        <label>Precio (costo)</label>
        <input type=\"number\" step=\"0.01\" name=\"precio\" value=\"{{ request.args.get('precio','') }}\" placeholder=\"Ej: 1000\">
      </div>
      <div class=\"field\">
        <label>Margen %</label>
        <input type=\"number\" step=\"0.01\" name=\"margen\" value=\"{{ request.args.get('margen','') }}\" placeholder=\"Ej: 20\">
      </div>
      <div class=\"actions\">
        <button type=\"submit\" class=\"button\">Calcular</button>
        <a class=\"button button-secondary\" href=\"{{ url_for('calculadora') }}\">Limpiar</a>
      </div>
    </form>

    {% if resultado is not none %}
    <div class=\"result\">
      <div><strong>Precio de venta:</strong> {{ "{:,.2f}".format(resultado) }}</div>
      <div><small>Fórmula: precio × 100 / (100 − margen)</small></div>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""
CALCULADORA_HTML = CALCULADORA_HTML.replace('</body>',
    '<script>\n'
    '  (function(){\n'
    '    const locale = "es-ES";\n'
    '    const nf0 = new Intl.NumberFormat(locale);\n'
    '    function unformat(val){\n'
    '      if(val == null) return "";\n'
    '      val = String(val).trim().replace(/\s/g, "");\n'
    '      if(/,\d{1,2}$/.test(val)){ val = val.replace(/\./g, "").replace(/,/g, "."); } else { val = val.replace(/\./g, ""); }\n'
    '      return val;\n'
    '    }\n'
    '    function parseNum(v){ const n = parseFloat(unformat(v)); return isNaN(n) ? null : n; }\n'
    '    const f = document.querySelector("form[action=\\"' + "{{ url_for('calculadora') }}" + '\\"]");\n'
    '    if(!f) return;\n'
    '    const precio = f.querySelector("input[name=precio]");\n'
    '    const margen = f.querySelector("input[name=margen]");\n'
    '    function formatEl(el){ const n = parseNum(el.value); if(n!=null) el.value = nf0.format(n); }\n'
    '    [precio, margen].forEach(el => {\n'
    '      if(!el) return;\n'
    '      el.addEventListener("blur", ()=>formatEl(el));\n'
    '      el.addEventListener("focus", ()=>{ el.value = unformat(el.value); });\n'
    '      if(el.value) formatEl(el);\n'
    '    });\n'
    '    f.addEventListener("submit", ()=>{\n'
    '      [precio, margen].forEach(el=>{ el.value = unformat(el.value); });\n'
    '    });\n'
    '  })();\n'
    '</script>\n</body>')


LEER_FACTURAS_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Leer facturas</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    a.button, button { display: inline-block; padding: 10px 16px; background: #1976d2; color: #fff; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; }
    a.button:hover, button:hover { background: #125a9e; }
    pre { background: #f7f7f7; padding: 12px; border-radius: 6px; overflow: auto; }
  </style>
</head>
<body>
  <a class="button" href="{{ url_for('menu') }}">← Volver</a>
  <h2>Leer facturas (IMAP)</h2>
  <form id="run-form" method="post" action="{{ url_for('leer_facturas_page') }}">
    <button type="submit" id="run-btn">{{ 'Procesando…' if running else 'Ejecutar procesamiento' }}</button>
  </form>

  <div id="status" style="margin-top:10px;">Estado: {{ 'En ejecución' if running else ('Finalizado' if finished else 'Idle') }}</div>

  <h3>Resultado</h3>
  <pre id="log" style="white-space: pre-wrap;">{{ salida or '' }}</pre>

  <script>
    (function(){
      const statusEl = document.getElementById('status');
      const logEl = document.getElementById('log');
      const btn = document.getElementById('run-btn');
      let polling = true;

      function tick(){
        fetch('{{ url_for('leer_facturas_status') }}').then(r=>r.json()).then(j=>{
          statusEl.textContent = 'Estado: ' + (j.running ? 'En ejecución' : (j.finished ? 'Finalizado' : 'Idle'));
          if(j.running){ btn.disabled = true; btn.textContent = 'Procesando…'; }
          else { btn.disabled = false; btn.textContent = 'Ejecutar procesamiento'; }
          if(typeof j.output === 'string'){
            logEl.textContent = j.output;
            // Auto-scroll al final
            logEl.scrollTop = logEl.scrollHeight;
          }
        }).catch(()=>{}).finally(()=>{
          if(polling) setTimeout(tick, 1500);
        });
      }
      tick();
    })();
  </script>
</body>
</html>
"""


def _template_precios():
    # Adaptamos el action="/" a action="/precios" y añadimos margen (%) y columna de venta
    tpl = precios.HTML_TEMPLATE
    tpl = tpl.replace('action="/"', 'action="/precios"')

    # Campo de margen debajo del filtro
    tpl = tpl.replace(
        '</label>\n    <br><br>',
        '</label>\n    <br>\n    <label>Margen %:</label>\n    <input name="margen" value="{{request.args.get(\'margen\',\'0\')}}" size="6">\n    <br><br>'
    )

    # Agregar columna en encabezado
    tpl = tpl.replace(
        '<tr><th>Proveedor</th><th>Fecha</th><th>Producto</th><th>Precio</th></tr>',
        '<tr><th>Proveedor</th><th>Fecha</th><th>Producto</th><th>Precio</th><th>Precio de venta</th></tr>'
    )

    # Reemplazar el bloque de filas para añadir la celda de precio_venta ya calculado
    tpl = tpl.replace(
        '        {% for r in rows %}\n          <tr>\n            <td>{{ r.proveedor }}</td>\n            <td>{{ r.fecha.strftime("%Y-%m-%d %H:%M:%S") if r.fecha else "" }}</td>\n            <td>{{ r.producto }}</td>\n            <td style="text-align:right;">{{ "{:,.2f}".format(r.precio) if r.precio is not none else "" }}</td>\n          </tr>\n        {% endfor %}\n',
        '        {% for r in rows %}\n          <tr>\n            <td>{{ r.proveedor }}</td>\n            <td>{{ r.fecha.strftime("%Y-%m-%d %H:%M:%S") if r.fecha else "" }}</td>\n            <td>{{ r.producto }}</td>\n            <td style="text-align:right;">{{ "{:,.2f}".format(r.precio) if r.precio is not none else "" }}</td>\n            <td style="text-align:right;">{{ "{:,.2f}".format(r.precio_venta) if r.precio_venta is not none else "" }}</td>\n          </tr>\n        {% endfor %}\n'
    )

    # Agregar estilos modernos
    tpl = tpl.replace(
        '</style>',
        '  .container { max-width: 1000px; margin: 0 auto; }\n'
        '  .form-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 10px 14px; align-items: start; }\n'
        '  .field { display: flex; flex-direction: column; min-width: 0; }\n'
        '  .form-grid label { font-weight: 600; display: block; margin-bottom: 6px; }\n'
        '  .form-grid input, .form-grid select { width: 100%; box-sizing: border-box; padding: 6px 8px; height: 34px; }\n'
        '  .actions { margin-top: 8px; display: flex; gap: 10px; align-items: center; }\n'
        '  .actions-row { grid-column: 1 / -1; display: flex; gap: 10px; }\n'
        '  a.button, button.button { display: inline-block; padding: 8px 14px; background: #1976d2; color: #fff; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; }\n'
        '  a.button:hover, button.button:hover { background: #125a9e; }\n'
        '  a.button-secondary { background: #777; }\n'
        '  a.button-secondary:hover { background: #5b5b5b; }\n'
        '  table tr:nth-child(even) { background: #fafafa; }\n'
        '</style>'
    )

    # Botón volver al menú
    tpl = tpl.replace(
        '<body>\n  <h2>',
        '<body>\n  <div class="container">\n    <div class="actions" style="margin-bottom:10px;">\n      <a class="button button-secondary" href="{{ url_for(\'menu\') }}">← Volver</a>\n    </div>\n    <h2>'
    )

    # Cerrar container al final del body
    tpl = tpl.replace('\n</body>', '\n  </div>\n</body>')

    # Convertir el formulario a grid y añadir placeholders y clases
    tpl = tpl.replace('<form method="get" action="/precios">', '<form method="get" action="/precios" class="form-grid">')

    # Fila 1: Proveedor, Producto
    tpl = tpl.replace(
        '    <label>Proveedor (parcial):</label><br>\n    <input name="proveedor"',
        '    <div class="field">\n      <label>Proveedor (parcial):</label>\n      <input name="proveedor" placeholder="Ej: Everest, Proveedor X"'
    )
    tpl = tpl.replace('<br>\n    <label>Producto (parcial):</label><br>\n    <input name="producto"',
        '</div>\n    <div class="field">\n      <label>Producto (parcial):</label>\n      <input name="producto" placeholder="Ej: PLC, cable, motor"'
    )
    tpl = tpl.replace('<br>\n    <label>Fecha inicio', '</div>\n    <div class="field">\n    <label>Fecha inicio')

    # Fila 2: Fecha inicio, Fecha fin
    tpl = tpl.replace('<input name="fecha_inicio"', '<input name="fecha_inicio" placeholder="YYYY-MM-DD [HH:MM[:SS]]"')
    tpl = tpl.replace('    <label style="margin-left:12px">Fecha fin (YYYY-MM-DD [HH:MM[:SS]]):</label><br>', '    </div>\n    <div class="field">\n      <label>Fecha fin (YYYY-MM-DD [HH:MM[:SS]]):</label>')
    tpl = tpl.replace('<input name="fecha_fin"', '<input name="fecha_fin" placeholder="YYYY-MM-DD [HH:MM[:SS]]"')
    tpl = tpl.replace('<br>\n    <label>Límite:', '</div>\n    <div class="field">\n    <label>Límite:')

    # Fila 3: Límite, Filtro, Margen
    tpl = tpl.replace('<input name="limite"', '<input name="limite"')
    tpl = tpl.replace('<label style="display:inline-block; margin-top:8px;">', '</div>\n    <div class="field">\n      <label>')
    tpl = tpl.replace('</label>\n    <br>', '</label>')
    tpl = tpl.replace('    <label>Margen %:</label>', '    </div>\n    <div class="field">\n      <label>Margen %:</label>')
    tpl = tpl.replace('<input name="margen"', '<input name="margen" placeholder="% margen"')

    # Fila 4: Acciones
    tpl = tpl.replace('<br><br>\n    <button type="submit">Buscar</button>\n    <a href="/">Limpiar</a>\n  </form>',
        '</div>\n    <div class="actions-row">\n      <a class="button button-secondary" href="/precios">Limpiar</a>\n      <button type="submit" class="button">Buscar</button>\n    </div>\n  </form>')

    # Agregar formateo de números (margen, límite) y normalización en submit
    script = (
        '<script>\n'
        '  (function(){\n'
        '    const locale = "es-ES";\n'
        '    const nf0 = new Intl.NumberFormat(locale);\n'
        '    function unformat(val){\n'
        '      if(val == null) return "";\n'
        '      val = String(val).trim();\n'
        '      val = val.replace(/\s/g,"");\n'
        '      if(/,\d{1,2}$/.test(val)){ val = val.replace(/\./g, "").replace(/,/g, "."); } else { val = val.replace(/\./g, ""); }\n'
        '      return val;\n'
        '    }\n'
        '    function tryParseFloat(val){\n'
        '      const raw = unformat(val);\n'
        '      const n = parseFloat(raw);\n'
        '      return isNaN(n) ? null : n;\n'
        '    }\n'
        '    function formatInput(el){\n'
        '      const n = tryParseFloat(el.value);\n'
        '      if(n == null) return;\n'
        '      if(el.name === "limite"){ el.value = nf0.format(Math.trunc(n)); } else { el.value = nf0.format(n); }\n'
        '    }\n'
        '    const form = document.querySelector("form[action=\"/precios\"]");\n'
        '    if(!form) return;\n'
        '    const inputs = Array.from(form.querySelectorAll("input[name=\"margen\"], input[name=\"limite\"]"));\n'
        '    inputs.forEach(el => {\n'
        '      el.addEventListener("blur", () => formatInput(el));\n'
        '      el.addEventListener("focus", () => { el.value = unformat(el.value); });\n'
        '      if(el.value) { formatInput(el); }\n'
        '    });\n'
        '    form.addEventListener("submit", () => {\n'
        '      inputs.forEach(el => { el.value = unformat(el.value); });\n'
        '    });\n'
        '  })();\n'
        '</script>'
    );
    tpl = tpl.replace('</html>', script + '\n</html>')

    return tpl


@app.route("/")
def menu():
    return render_template_string(MENU_HTML)
_job_state = {"running": False, "output": "", "finished": False, "started_at": None}
_job_lock = Lock()

def _run_leer_facturas_job():
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            facturas.procesar_correos()
        except Exception as e:
            print(f"❌ Error: {e}")
    # Guardar salida y marcar fin
    with _job_lock:
        _job_state["output"] = buf.getvalue()
        _job_state["running"] = False
        _job_state["finished"] = True


@app.route("/precios", methods=["GET"])
def precios_index():
    proveedor = request.args.get("proveedor") or None
    producto = request.args.get("producto") or None
    fecha_inicio_raw = request.args.get("fecha_inicio") or None
    fecha_fin_raw = request.args.get("fecha_fin") or None
    limite = request.args.get("limite") or "200"
    filtro = request.args.get("filtro") or "sin"
    margen_str = request.args.get("margen") or "0"
    try:
        limite = int(limite)
    except ValueError:
        limite = 200
    try:
        margen_val = float(margen_str)
    except ValueError:
        margen_val = 0.0

    rows = None
    if any((proveedor, producto, fecha_inicio_raw, fecha_fin_raw)) or request.args.get("limite") or request.args.get("filtro"):
        fi = precios.parse_fecha(fecha_inicio_raw, inicio=True)
        ff = precios.parse_fecha(fecha_fin_raw, inicio=False)
        conn, cur = precios.conectar()
        try:
            fetched = precios.buscar_precios_db(cur, proveedor=proveedor, producto=producto, fecha_inicio=fi, fecha_fin=ff, limite=limite, filtro=filtro)
        finally:
            cur.close()
            conn.close()
        # Enriquecer filas con precio_venta calculado
        rows = []
        for r in fetched or []:
            precio = r["precio"]
            proveedor_val = r["proveedor"]
            fecha_val = r["fecha"]
            producto_val = r["producto"]
            precio_venta = None
            try:
                if precio is not None and (100.0 - margen_val) != 0.0:
                    precio_venta = float(precio) * 100.0 / (100.0 - margen_val)
            except Exception:
                precio_venta = None
            rows.append({
                "proveedor": proveedor_val,
                "fecha": fecha_val,
                "producto": producto_val,
                "precio": precio,
                "precio_venta": precio_venta,
            })

    return render_template_string(_template_precios(), rows=rows, request=request, margen_val=margen_val)


@app.route("/leer-facturas", methods=["GET", "POST"])
def leer_facturas_page():
    if request.method == "POST":
        with _job_lock:
            if not _job_state["running"]:
                _job_state["running"] = True
                _job_state["finished"] = False
                _job_state["output"] = ""
                _job_state["started_at"] = time.time()
                t = Thread(target=_run_leer_facturas_job, daemon=True)
                t.start()
    with _job_lock:
        running = _job_state["running"]
        finished = _job_state["finished"]
        salida = _job_state["output"]
    return render_template_string(LEER_FACTURAS_HTML, salida=salida, running=running, finished=finished)

@app.route("/leer-facturas/status", methods=["GET"])
def leer_facturas_status():
    with _job_lock:
        return jsonify({
            "running": _job_state["running"],
            "finished": _job_state["finished"],
            "output": _job_state["output"],
        })


@app.route("/calculadora", methods=["GET"])
def calculadora():
    precio_str = request.args.get("precio")
    margen_str = request.args.get("margen")
    resultado = None
    try:
        if precio_str is not None and margen_str is not None:
            precio_val = float(precio_str)
            margen_val = float(margen_str)
            if (100.0 - margen_val) != 0.0:
                resultado = precio_val * 100.0 / (100.0 - margen_val)
    except ValueError:
        resultado = None
    return render_template_string(CALCULADORA_HTML, request=request, resultado=resultado)


if __name__ == "__main__":
    # App unificada
    app.run(host="127.0.0.1", port=5000, debug=True)


