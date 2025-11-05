from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, time
import psycopg2
import psycopg2.extras
import os

load_dotenv()

PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Buscar precios</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    input, select, button { padding: 6px; margin: 4px 0; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border: 1px solid #ddd; padding: 8px; }
    th { background: #f2f2f2; text-align: left; }
  </style>
</head>
<body>
  <h2>Buscar en la base de datos de precios</h2>
  <form method="get" action="/">
    <label>Proveedor (parcial):</label><br>
    <input name="proveedor" value="{{request.args.get('proveedor','')}}" size="50"><br>
    <label>Producto (parcial):</label><br>
    <input name="producto" value="{{request.args.get('producto','')}}" size="50"><br>
    <label>Fecha inicio (YYYY-MM-DD [HH:MM[:SS]]):</label><br>
    <input name="fecha_inicio" value="{{request.args.get('fecha_inicio','')}}" size="25">
    <label style="margin-left:12px">Fecha fin (YYYY-MM-DD [HH:MM[:SS]]):</label><br>
    <input name="fecha_fin" value="{{request.args.get('fecha_fin','')}}" size="25"><br>
    <label>Límite:</label>
    <input name="limite" value="{{request.args.get('limite','200')}}" size="6">
    <br>
    <label style="display:inline-block; margin-top:8px;">
      Filtro: 
      <select name="filtro">
        <option value="sin" {% if request.args.get('filtro','sin') == 'sin' %}selected{% endif %}>SIN FILTRO</option>
        <option value="actual" {% if request.args.get('filtro') == 'actual' %}selected{% endif %}>PRECIO MÁS ACTUAL</option>
        <option value="alto" {% if request.args.get('filtro') == 'alto' %}selected{% endif %}>PRECIO MÁS ALTO</option>
        <option value="bajo" {% if request.args.get('filtro') == 'bajo' %}selected{% endif %}>PRECIO MÁS BAJO</option>
      </select>
    </label>
    <br><br>
    <button type="submit">Buscar</button>
    <a href="/">Limpiar</a>
  </form>

  {% if rows is not none %}
    <h3>Resultados ({{rows|length}})</h3>
    {% if rows|length == 0 %}
      <p>No se encontraron resultados.</p>
    {% else %}
      <table>
        <tr><th>Proveedor</th><th>Fecha</th><th>Producto</th><th>Precio</th></tr>
        {% for r in rows %}
          <tr>
            <td>{{ r.proveedor }}</td>
            <td>{{ r.fecha.strftime("%Y-%m-%d %H:%M:%S") if r.fecha else "" }}</td>
            <td>{{ r.producto }}</td>
            <td style="text-align:right;">{{ "{:,.2f}".format(r.precio) if r.precio is not none else "" }}</td>
          </tr>
        {% endfor %}
      </table>
    {% endif %}
  {% endif %}
</body>
</html>
"""

def conectar():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur

def parse_fecha(texto, inicio=True):
    if not texto:
        return None
    texto = texto.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(texto, fmt)
            if fmt == "%Y-%m-%d" and inicio is False:
                # fin del día
                return datetime.combine(dt.date(), time(23,59,59))
            if fmt == "%Y-%m-%d" and inicio is True:
                return datetime.combine(dt.date(), time(0,0,0))
            return dt
        except ValueError:
            continue
    return None

def buscar_precios_db(cur, proveedor=None, producto=None, fecha_inicio=None, fecha_fin=None, limite=200, filtro="sin"):
    params = []
    # Construir WHERE dinámico
    where_clauses = []
    if proveedor:
        where_clauses.append("proveedor ILIKE %s")
        params.append(f"%{proveedor}%")
    if producto:
        where_clauses.append("producto ILIKE %s")
        params.append(f"%{producto}%")
    if fecha_inicio:
        where_clauses.append("fecha >= %s")
        params.append(fecha_inicio)
    if fecha_fin:
        where_clauses.append("fecha <= %s")
        params.append(fecha_fin)

    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    # Según filtro, construimos consulta que devuelve una fila por (proveedor, producto)
    if filtro == "actual":
        sql = f"""
            WITH ranked AS (
                SELECT
                    proveedor,
                    fecha,
                    producto,
                    precio,
                    ROW_NUMBER() OVER (
                        PARTITION BY proveedor, producto
                        ORDER BY (fecha::timestamp) DESC NULLS LAST
                    ) AS rn
                FROM precios
                {where_sql}
            )
            SELECT proveedor, fecha, producto, precio
            FROM ranked
            WHERE rn = 1
            ORDER BY fecha DESC NULLS LAST
            LIMIT %s
        """
        params.append(limite)
    elif filtro == "alto":
        sql = f"""
            WITH ranked AS (
                SELECT
                    proveedor,
                    fecha,
                    producto,
                    precio,
                    ROW_NUMBER() OVER (
                        PARTITION BY proveedor, producto
                        ORDER BY (precio::numeric) DESC NULLS LAST, (fecha::timestamp) DESC NULLS LAST
                    ) AS rn
                FROM precios
                {where_sql}
            )
            SELECT proveedor, fecha, producto, precio
            FROM ranked
            WHERE rn = 1
            ORDER BY precio::numeric DESC NULLS LAST
            LIMIT %s
        """
        params.append(limite)
    elif filtro == "bajo":
        sql = f"""
            WITH ranked AS (
                SELECT
                    proveedor,
                    fecha,
                    producto,
                    precio,
                    ROW_NUMBER() OVER (
                        PARTITION BY proveedor, producto
                        ORDER BY (precio::numeric) ASC NULLS LAST, (fecha::timestamp) DESC NULLS LAST
                    ) AS rn
                FROM precios
                {where_sql}
            )
            SELECT proveedor, fecha, producto, precio
            FROM ranked
            WHERE rn = 1
            ORDER BY precio::numeric ASC NULLS LAST
            LIMIT %s
        """
        params.append(limite)
    else:  # "sin" o cualquier otro valor -> sin agrupamiento
        sql = f"""
            SELECT proveedor, fecha, producto, precio
            FROM precios
            {where_sql}
            ORDER BY (fecha::timestamp) DESC NULLS LAST
            LIMIT %s
        """
        params.append(limite)

    cur.execute(sql, tuple(params))
    return cur.fetchall()

@app.route("/", methods=["GET"])
def index():
    proveedor = request.args.get("proveedor") or None
    producto = request.args.get("producto") or None
    fecha_inicio_raw = request.args.get("fecha_inicio") or None
    fecha_fin_raw = request.args.get("fecha_fin") or None
    limite = request.args.get("limite") or "200"
    filtro = request.args.get("filtro") or "sin"
    try:
        limite = int(limite)
    except ValueError:
        limite = 200

    rows = None
    if any((proveedor, producto, fecha_inicio_raw, fecha_fin_raw)) or request.args.get("limite") or request.args.get("filtro"):
        fi = parse_fecha(fecha_inicio_raw, inicio=True)
        ff = parse_fecha(fecha_fin_raw, inicio=False)
        conn, cur = conectar()
        try:
            rows = buscar_precios_db(cur, proveedor=proveedor, producto=producto, fecha_inicio=fi, fecha_fin=ff, limite=limite, filtro=filtro)
        finally:
            cur.close()
            conn.close()

    return render_template_string(HTML_TEMPLATE, rows=rows, request=request)

@app.route("/api/search", methods=["GET"])
def api_search():
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

    fi = parse_fecha(fecha_inicio_raw, inicio=True)
    ff = parse_fecha(fecha_fin_raw, inicio=False)
    try:
        margen_val = float(margen_str)
    except ValueError:
        margen_val = 0.0

    conn, cur = conectar()
    try:
        rows = buscar_precios_db(cur, proveedor=proveedor, producto=producto, fecha_inicio=fi, fecha_fin=ff, limite=limite, filtro=filtro)
    finally:
        cur.close()
        conn.close()

    out = []
    for r in rows:
        precio_val = float(r["precio"]) if r["precio"] is not None else None
        precio_venta = None
        if precio_val is not None and (100 - margen_val) != 0:
            precio_venta = precio_val / ((100 - margen_val)/100)
        out.append({
            "proveedor": r["proveedor"],
            "fecha": r["fecha"].isoformat() if r["fecha"] else None,
            "producto": r["producto"],
            "precio": precio_val,
            "precio_venta": precio_venta
        })
    return jsonify(out)

if __name__ == "__main__":
    # Ejecutar en modo desarrollo. En producción usar WSGI (gunicorn/uvicorn) y configurar host/puerto.
    app.run(host="127.0.0.1", port=5000, debug=True)