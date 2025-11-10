from flask import Flask
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