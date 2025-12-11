"""
Módulo de reportes de clientes
Maneja la consulta y cálculo de reportes de facturas por cliente
"""
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv
from datetime import datetime, date, timedelta

load_dotenv()

PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}


def conectar():
    """Conecta a la base de datos"""
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur


def calcular_estado_pago(fecha_vencimiento, fecha_pago, tipo_venta):
    """Calcula el estado de pago basado en fechas"""
    if tipo_venta == 'Contado':
        return 'pagado'
    
    if not fecha_vencimiento:
        return 'pendiente'
    
    hoy = date.today()
    
    # Si tiene fecha de pago
    if fecha_pago:
        if fecha_pago < fecha_vencimiento:
            return 'adelantado'
        elif fecha_pago > fecha_vencimiento:
            return 'atrasado'
        else:
            return 'en_dia'
    
    # Si no tiene fecha de pago, comparar con fecha de vencimiento
    if hoy < fecha_vencimiento:
        return 'pendiente'
    elif hoy == fecha_vencimiento:
        return 'en_dia'
    else:
        return 'atrasado'


def calcular_dias_atraso(fecha_vencimiento, fecha_pago, tipo_venta):
    """Calcula los días de atraso"""
    if tipo_venta == 'Contado':
        return 0
    
    if not fecha_vencimiento:
        return 0
    
    # Si tiene fecha de pago, calcular diferencia
    if fecha_pago:
        if fecha_pago > fecha_vencimiento:
            return (fecha_pago - fecha_vencimiento).days
        else:
            return 0
    
    # Si no tiene fecha de pago y ya venció, calcular desde hoy
    hoy = date.today()
    if hoy > fecha_vencimiento:
        return (hoy - fecha_vencimiento).days
    
    return 0


def obtener_reportes_cliente(cliente_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None):
    """Obtiene reportes de facturas y cuentas a recibir de un cliente o todos los clientes"""
    conn, cur = conectar()
    try:
        reportes = []
        
        # ========== OBTENER FACTURAS ==========
        where_clauses = []
        params = []
        
        if cliente_nombre:
            where_clauses.append("UPPER(f.cliente) LIKE UPPER(%s)")
            params.append(f"%{cliente_nombre}%")
        
        if fecha_desde:
            where_clauses.append("f.fecha >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("f.fecha <= %s")
            params.append(fecha_hasta)
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Query principal de facturas
        query = f"""
            SELECT 
                f.id,
                f.numero_factura,
                f.fecha,
                f.cliente,
                f.ruc,
                f.moneda,
                f.tipo_venta,
                f.plazo_dias,
                f.fecha_vencimiento,
                f.fecha_pago,
                f.estado_pago,
                f.total_general,
                f.creado_en
            FROM facturas f
            {where_sql}
            ORDER BY f.fecha DESC, f.numero_factura DESC
        """
        
        cur.execute(query, params)
        facturas = cur.fetchall()
        
        # Procesar facturas y calcular estados
        for factura in facturas:
            # Convertir fecha_emision a date (siempre necesario)
            fecha_emision = factura['fecha']
            if isinstance(fecha_emision, str):
                fecha_emision = datetime.strptime(fecha_emision, "%Y-%m-%d").date()
            elif isinstance(fecha_emision, datetime):
                fecha_emision = fecha_emision.date()
            
            # Asegurar que fecha_vencimiento esté calculada si es crédito
            fecha_vencimiento = factura['fecha_vencimiento']
            if fecha_vencimiento:
                if isinstance(fecha_vencimiento, str):
                    fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
                elif isinstance(fecha_vencimiento, datetime):
                    fecha_vencimiento = fecha_vencimiento.date()
            elif factura['tipo_venta'] == 'Crédito' and factura['plazo_dias']:
                # Calcular fecha_vencimiento si no existe y es crédito
                fecha_vencimiento = fecha_emision + timedelta(days=factura['plazo_dias'])
            
            # Para contado, fecha de pago = fecha de emisión si no está establecida
            fecha_pago = factura['fecha_pago']
            if fecha_pago:
                if isinstance(fecha_pago, str):
                    fecha_pago = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
                elif isinstance(fecha_pago, datetime):
                    fecha_pago = fecha_pago.date()
            elif factura['tipo_venta'] == 'Contado':
                # Para contado, fecha de pago = fecha de emisión
                fecha_pago = fecha_emision
            
            # Convertir fecha_pago a date si es string
            if fecha_pago and isinstance(fecha_pago, str):
                fecha_pago = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
            elif fecha_pago and isinstance(fecha_pago, datetime):
                fecha_pago = fecha_pago.date()
            
            # Calcular estado y días de atraso
            estado = calcular_estado_pago(fecha_vencimiento, fecha_pago, factura['tipo_venta'])
            dias_atraso = calcular_dias_atraso(fecha_vencimiento, fecha_pago, factura['tipo_venta'])
            
            # Traducir estado a español
            estado_espanol = {
                'pagado': 'Pagado',
                'pendiente': 'Pendiente',
                'en_dia': 'En día',
                'atrasado': 'Atrasado',
                'adelantado': 'Adelantado'
            }.get(estado, estado)
            
            reporte = {
                'tipo': 'FACTURA',
                'id': factura['id'],
                'numero_factura': factura['numero_factura'],
                'fecha_emision': fecha_emision,
                'cliente': factura['cliente'],
                'ruc': factura['ruc'],
                'moneda': factura['moneda'],
                'tipo_venta': factura['tipo_venta'],
                'plazo_dias': factura['plazo_dias'],
                'fecha_vencimiento': fecha_vencimiento,
                'fecha_pago': fecha_pago,
                'estado_pago': estado_espanol,
                'dias_atraso': dias_atraso,
                'monto': float(factura['total_general']) if factura['total_general'] else 0
            }
            
            reportes.append(reporte)
        
        # ========== OBTENER CUENTAS A RECIBIR ==========
        where_clauses_car = []
        params_car = []
        
        if cliente_nombre:
            where_clauses_car.append("UPPER(car.cliente) LIKE UPPER(%s)")
            params_car.append(f"%{cliente_nombre}%")
        
        if fecha_desde:
            where_clauses_car.append("car.fecha_emision >= %s")
            params_car.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses_car.append("car.fecha_emision <= %s")
            params_car.append(fecha_hasta)
        
        where_sql_car = ""
        if where_clauses_car:
            where_sql_car = "WHERE " + " AND ".join(where_clauses_car)
        
        # Query de cuentas a recibir
        query_car = f"""
            SELECT 
                car.id,
                car.fecha_emision,
                car.cliente,
                car.factura,
                car.descripcion,
                car.valor,
                car.valor_cuota,
                car.cuotas,
                car.vencimiento,
                car.fecha_recibo,
                car.estado,
                car.status_recibo,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                ci.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre
            FROM cuentas_a_recibir car
            LEFT JOIN tipos_documentos td ON car.documento_id = td.id
            LEFT JOIN bancos b ON car.banco_id = b.id
            LEFT JOIN categorias_ingresos ci ON car.cuenta_id = ci.id
            LEFT JOIN proyectos p ON car.proyecto_id = p.id
            {where_sql_car}
            ORDER BY car.fecha_emision DESC, car.id DESC
        """
        
        cur.execute(query_car, params_car)
        cuentas_a_recibir = cur.fetchall()
        
        # Procesar cuentas a recibir
        for cuenta in cuentas_a_recibir:
            fecha_emision_car = cuenta['fecha_emision']
            if isinstance(fecha_emision_car, str):
                fecha_emision_car = datetime.strptime(fecha_emision_car, "%Y-%m-%d").date()
            elif isinstance(fecha_emision_car, datetime):
                fecha_emision_car = fecha_emision_car.date()
            
            fecha_vencimiento_car = cuenta['vencimiento']
            if fecha_vencimiento_car:
                if isinstance(fecha_vencimiento_car, str):
                    fecha_vencimiento_car = datetime.strptime(fecha_vencimiento_car, "%Y-%m-%d").date()
                elif isinstance(fecha_vencimiento_car, datetime):
                    fecha_vencimiento_car = fecha_vencimiento_car.date()
            
            fecha_recibo_car = cuenta['fecha_recibo']
            if fecha_recibo_car:
                if isinstance(fecha_recibo_car, str):
                    fecha_recibo_car = datetime.strptime(fecha_recibo_car, "%Y-%m-%d").date()
                elif isinstance(fecha_recibo_car, datetime):
                    fecha_recibo_car = fecha_recibo_car.date()
            
            # Calcular días de atraso para cuentas a recibir
            dias_atraso_car = 0
            if fecha_vencimiento_car:
                if fecha_recibo_car:
                    if fecha_recibo_car > fecha_vencimiento_car:
                        dias_atraso_car = (fecha_recibo_car - fecha_vencimiento_car).days
                else:
                    hoy = date.today()
                    if hoy > fecha_vencimiento_car:
                        dias_atraso_car = (hoy - fecha_vencimiento_car).days
            
            # Determinar estado de pago
            estado_pago_car = cuenta['estado'] or 'ABIERTO'
            if estado_pago_car == 'RECIBIDO':
                estado_pago_car = 'Pagado'
            elif estado_pago_car == 'ABIERTO':
                if fecha_vencimiento_car:
                    hoy = date.today()
                    if hoy > fecha_vencimiento_car:
                        estado_pago_car = 'Atrasado'
                    elif hoy == fecha_vencimiento_car:
                        estado_pago_car = 'En día'
                    else:
                        estado_pago_car = 'Pendiente'
                else:
                    estado_pago_car = 'Pendiente'
            
            # Usar status_recibo si está disponible
            if cuenta['status_recibo']:
                status_map = {
                    'ADELANTADO': 'Adelantado',
                    'ATRASADO': 'Atrasado',
                    'EN DIA': 'En día'
                }
                estado_pago_car = status_map.get(cuenta['status_recibo'], estado_pago_car)
            
            reporte_car = {
                'tipo': 'CUENTA_A_RECIBIR',
                'id': cuenta['id'],
                'numero_factura': cuenta['factura'] or f"CAR-{cuenta['id']}",
                'fecha_emision': fecha_emision_car,
                'cliente': cuenta['cliente'],
                'ruc': None,  # Las cuentas a recibir no tienen RUC
                'moneda': 'Gs',  # Por defecto
                'tipo_venta': cuenta.get('tipo', 'FCON'),
                'plazo_dias': None,
                'fecha_vencimiento': fecha_vencimiento_car,
                'fecha_pago': fecha_recibo_car,
                'estado_pago': estado_pago_car,
                'dias_atraso': dias_atraso_car,
                'monto': float(cuenta['valor']) if cuenta['valor'] else 0,
                # Campos adicionales de cuentas a recibir
                'documento_nombre': cuenta.get('documento_nombre'),
                'banco_nombre': cuenta.get('banco_nombre'),
                'cuenta_nombre': cuenta.get('cuenta_nombre'),
                'proyecto_nombre': cuenta.get('proyecto_nombre'),
                'descripcion': cuenta.get('descripcion'),
                'cuotas': cuenta.get('cuotas'),
                'valor_cuota': float(cuenta['valor_cuota']) if cuenta['valor_cuota'] else None
            }
            
            reportes.append(reporte_car)
        
        # Ordenar todos los reportes por fecha de emisión descendente
        reportes.sort(key=lambda x: x['fecha_emision'] if x['fecha_emision'] else date.min, reverse=True)
        
        return reportes
    finally:
        cur.close()
        conn.close()


def obtener_clientes_con_facturas():
    """Obtiene lista de clientes que tienen facturas o cuentas a recibir"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT DISTINCT cliente, ruc
            FROM facturas
            WHERE cliente IS NOT NULL
            UNION
            SELECT DISTINCT cliente, NULL as ruc
            FROM cuentas_a_recibir
            WHERE cliente IS NOT NULL
            ORDER BY cliente
        """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def contar_reportes_cuentas_a_pagar(proveedor_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None):
    """Cuenta el total de reportes de cuentas a pagar según los filtros"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if proveedor_nombre:
            where_clauses.append("UPPER(cap.proveedor) LIKE UPPER(%s)")
            params.append(f"%{proveedor_nombre}%")
        
        if fecha_desde:
            where_clauses.append("cap.fecha_emision >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("cap.fecha_emision <= %s")
            params.append(fecha_hasta)
        
        if tipo_filtro:
            where_clauses.append("cap.tipo = %s")
            params.append(tipo_filtro)
        
        if estado_pago_filtro:
            if estado_pago_filtro.lower() == 'pagado':
                where_clauses.append("cap.estado = 'PAGADO'")
            elif estado_pago_filtro.lower() == 'pendiente':
                where_clauses.append("cap.estado = 'ABIERTO'")
            elif estado_pago_filtro.lower() == 'atrasado':
                where_clauses.append("(cap.estado = 'ABIERTO' AND cap.vencimiento < CURRENT_DATE) OR cap.status_pago = 'ATRASADO'")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        query = f"""
            SELECT COUNT(*)
            FROM cuentas_a_pagar cap
            {where_sql}
        """
        
        cur.execute(query, params)
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def obtener_reportes_cuentas_a_pagar(proveedor_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None, limite=None, offset=None):
    """Obtiene reportes de cuentas a pagar de un proveedor o todos los proveedores"""
    conn, cur = conectar()
    try:
        reportes = []
        
        # ========== OBTENER CUENTAS A PAGAR ==========
        where_clauses = []
        params = []
        
        if proveedor_nombre:
            where_clauses.append("UPPER(cap.proveedor) LIKE UPPER(%s)")
            params.append(f"%{proveedor_nombre}%")
        
        if fecha_desde:
            where_clauses.append("cap.fecha_emision >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("cap.fecha_emision <= %s")
            params.append(fecha_hasta)
        
        if tipo_filtro:
            where_clauses.append("cap.tipo = %s")
            params.append(tipo_filtro)
        
        if estado_pago_filtro:
            if estado_pago_filtro.lower() == 'pagado':
                where_clauses.append("cap.estado = 'PAGADO'")
            elif estado_pago_filtro.lower() == 'pendiente':
                where_clauses.append("cap.estado = 'ABIERTO'")
            elif estado_pago_filtro.lower() == 'atrasado':
                where_clauses.append("(cap.estado = 'ABIERTO' AND cap.vencimiento < CURRENT_DATE) OR cap.status_pago = 'ATRASADO'")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Agregar LIMIT y OFFSET si se proporcionan
        limit_sql = ""
        if limite is not None:
            limit_sql = f"LIMIT {limite}"
            if offset is not None:
                limit_sql += f" OFFSET {offset}"
        
        # Query de cuentas a pagar
        query = f"""
            SELECT 
                cap.id,
                cap.fecha_emision,
                cap.proveedor,
                cap.factura,
                cap.descripcion,
                cap.valor,
                cap.valor_cuota,
                cap.monto_abonado,
                cap.cuotas,
                cap.vencimiento,
                cap.fecha_pago,
                cap.estado,
                cap.status_pago,
                cap.tipo,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                cg.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre
            FROM cuentas_a_pagar cap
            LEFT JOIN tipos_documentos td ON cap.documento_id = td.id
            LEFT JOIN bancos b ON cap.banco_id = b.id
            LEFT JOIN categorias_gastos cg ON cap.cuenta_id = cg.id
            LEFT JOIN proyectos p ON cap.proyecto_id = p.id
            {where_sql}
            ORDER BY cap.fecha_emision DESC, cap.id DESC
            {limit_sql}
        """
        
        cur.execute(query, params)
        cuentas_a_pagar = cur.fetchall()
        
        # Procesar cuentas a pagar
        for cuenta in cuentas_a_pagar:
            fecha_emision = cuenta['fecha_emision']
            if isinstance(fecha_emision, str):
                fecha_emision = datetime.strptime(fecha_emision, "%Y-%m-%d").date()
            elif isinstance(fecha_emision, datetime):
                fecha_emision = fecha_emision.date()
            
            fecha_vencimiento = cuenta['vencimiento']
            if fecha_vencimiento:
                if isinstance(fecha_vencimiento, str):
                    fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
                elif isinstance(fecha_vencimiento, datetime):
                    fecha_vencimiento = fecha_vencimiento.date()
            
            fecha_pago = cuenta['fecha_pago']
            if fecha_pago:
                if isinstance(fecha_pago, str):
                    fecha_pago = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
                elif isinstance(fecha_pago, datetime):
                    fecha_pago = fecha_pago.date()
            
            # Calcular días de atraso
            dias_atraso = 0
            estado_pago_detalle = None  # Para indicar si fue adelantado, en día o atrasado cuando está pagado
            
            if fecha_vencimiento:
                if fecha_pago:
                    # Si tiene fecha de pago, calcular días de atraso/adelanto
                    if fecha_pago > fecha_vencimiento:
                        dias_atraso = (fecha_pago - fecha_vencimiento).days
                        estado_pago_detalle = 'Atrasado'
                    elif fecha_pago < fecha_vencimiento:
                        dias_atraso = (fecha_vencimiento - fecha_pago).days
                        estado_pago_detalle = 'Adelantado'
                    else:
                        dias_atraso = 0
                        estado_pago_detalle = 'En día'
                else:
                    # Sin fecha de pago, calcular días de atraso desde hoy
                    hoy = date.today()
                    if hoy > fecha_vencimiento:
                        dias_atraso = (hoy - fecha_vencimiento).days
            
            # Determinar estado de pago
            estado_pago = cuenta['estado'] or 'ABIERTO'
            
            # Si tiene fecha de pago, siempre es "Pagado" pero con detalle
            if fecha_pago:
                if estado_pago_detalle:
                    estado_pago = f'Pagado ({estado_pago_detalle})'
                else:
                    estado_pago = 'Pagado'
            elif estado_pago == 'PAGADO':
                # Si está marcado como PAGADO pero no tiene fecha_pago, solo mostrar "Pagado"
                estado_pago = 'Pagado'
            elif estado_pago == 'ABIERTO':
                if fecha_vencimiento:
                    hoy = date.today()
                    if hoy > fecha_vencimiento:
                        estado_pago = 'Atrasado'
                    elif hoy == fecha_vencimiento:
                        estado_pago = 'En día'
                    else:
                        estado_pago = 'Pendiente'
                else:
                    estado_pago = 'Pendiente'
            
            # Usar status_pago si está disponible (solo si no tiene fecha_pago)
            if cuenta['status_pago'] and not fecha_pago:
                status_map = {
                    'ADELANTADO': 'Adelantado',
                    'ATRASADO': 'Atrasado',
                    'EN DIA': 'En día'
                }
                estado_pago = status_map.get(cuenta['status_pago'], estado_pago)
            
            # Calcular saldo: (valor_cuota o valor) - monto_abonado
            valor_cuota = float(cuenta['valor_cuota']) if cuenta['valor_cuota'] else None
            valor = float(cuenta['valor']) if cuenta['valor'] else 0
            monto_abonado = float(cuenta.get('monto_abonado') or 0)
            monto_comparar = valor_cuota if valor_cuota is not None else valor
            
            # Calcular saldo correctamente
            # El saldo es la diferencia entre lo que se debe y lo que se ha abonado
            if monto_comparar is not None:
                # Para valores positivos: saldo = valor - monto_abonado
                # Para valores negativos (NCRE): el monto_abonado se guarda como positivo,
                # pero conceptualmente es negativo, entonces: saldo = valor + monto_abonado
                if monto_comparar < 0:
                    # NCRE: el valor es negativo, el monto_abonado es positivo pero conceptualmente negativo
                    saldo = monto_comparar + monto_abonado
                    # Si el saldo es positivo (se pagó de más), poner 0
                    if saldo > 0:
                        saldo = 0
                else:
                    # Valor positivo: saldo = valor - monto_abonado
                    saldo = monto_comparar - monto_abonado
                    # Si el saldo queda negativo (se pagó de más), poner 0
                    if saldo < 0:
                        saldo = 0
            else:
                saldo = 0
            
            reporte = {
                'tipo': 'CUENTA_A_PAGAR',
                'id': cuenta['id'],
                'numero_factura': cuenta['factura'] or f"CAP-{cuenta['id']}",
                'fecha_emision': fecha_emision,
                'proveedor': cuenta['proveedor'],
                'ruc': None,
                'moneda': 'Gs',
                'tipo_venta': cuenta.get('tipo', 'FCON'),
                'plazo_dias': None,
                'fecha_vencimiento': fecha_vencimiento,
                'fecha_pago': fecha_pago,
                'estado_pago': estado_pago,
                'dias_atraso': dias_atraso,
                'monto': saldo,  # Mostrar saldo en lugar del monto total
                # Campos adicionales
                'documento_nombre': cuenta.get('documento_nombre'),
                'banco_nombre': cuenta.get('banco_nombre'),
                'cuenta_nombre': cuenta.get('cuenta_nombre'),
                'proyecto_nombre': cuenta.get('proyecto_nombre'),
                'descripcion': cuenta.get('descripcion'),
                'cuotas': cuenta.get('cuotas'),
                'valor_cuota': float(cuenta['valor_cuota']) if cuenta['valor_cuota'] else None
            }
            
            reportes.append(reporte)
        
        # Ordenar por fecha de emisión descendente
        reportes.sort(key=lambda x: x['fecha_emision'] if x['fecha_emision'] else date.min, reverse=True)
        
        return reportes
    finally:
        cur.close()
        conn.close()


def obtener_proveedores_con_cuentas():
    """Obtiene lista de proveedores que tienen cuentas a pagar"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT DISTINCT proveedor, NULL as ruc
            FROM cuentas_a_pagar
            WHERE proveedor IS NOT NULL
            ORDER BY proveedor
        """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def contar_reportes_cuentas_a_recibir(cliente_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None):
    """Cuenta el total de reportes de cuentas a recibir según los filtros"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if cliente_nombre:
            where_clauses.append("UPPER(car.cliente) LIKE UPPER(%s)")
            params.append(f"%{cliente_nombre}%")
        
        if fecha_desde:
            where_clauses.append("car.fecha_emision >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("car.fecha_emision <= %s")
            params.append(fecha_hasta)
        
        if tipo_filtro:
            where_clauses.append("car.tipo = %s")
            params.append(tipo_filtro)
        
        if estado_pago_filtro:
            if estado_pago_filtro.lower() == 'pagado' or estado_pago_filtro.lower() == 'recibido':
                where_clauses.append("car.estado = 'RECIBIDO'")
            elif estado_pago_filtro.lower() == 'pendiente':
                where_clauses.append("car.estado = 'ABIERTO'")
            elif estado_pago_filtro.lower() == 'atrasado':
                where_clauses.append("(car.estado = 'ABIERTO' AND car.vencimiento < CURRENT_DATE) OR car.status_recibo = 'ATRASADO'")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        query = f"""
            SELECT COUNT(*)
            FROM cuentas_a_recibir car
            {where_sql}
        """
        
        cur.execute(query, params)
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def obtener_reportes_cuentas_a_recibir(cliente_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None, limite=None, offset=None):
    """Obtiene reportes de cuentas a recibir de un cliente o todos los clientes"""
    conn, cur = conectar()
    try:
        reportes = []
        
        # ========== OBTENER CUENTAS A RECIBIR ==========
        where_clauses = []
        params = []
        
        if cliente_nombre:
            where_clauses.append("UPPER(car.cliente) LIKE UPPER(%s)")
            params.append(f"%{cliente_nombre}%")
        
        if fecha_desde:
            where_clauses.append("car.fecha_emision >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("car.fecha_emision <= %s")
            params.append(fecha_hasta)
        
        if tipo_filtro:
            where_clauses.append("car.tipo = %s")
            params.append(tipo_filtro)
        
        if estado_pago_filtro:
            if estado_pago_filtro.lower() == 'pagado' or estado_pago_filtro.lower() == 'recibido':
                where_clauses.append("car.estado = 'RECIBIDO'")
            elif estado_pago_filtro.lower() == 'pendiente':
                where_clauses.append("car.estado = 'ABIERTO'")
            elif estado_pago_filtro.lower() == 'atrasado':
                where_clauses.append("(car.estado = 'ABIERTO' AND car.vencimiento < CURRENT_DATE) OR car.status_recibo = 'ATRASADO'")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Agregar LIMIT y OFFSET si se proporcionan
        limit_sql = ""
        if limite is not None:
            limit_sql = f"LIMIT {limite}"
            if offset is not None:
                limit_sql += f" OFFSET {offset}"
        
        # Query de cuentas a recibir
        query = f"""
            SELECT 
                car.id,
                car.fecha_emision,
                car.cliente,
                car.factura,
                car.descripcion,
                car.valor,
                car.valor_cuota,
                car.monto_abonado,
                car.cuotas,
                car.vencimiento,
                car.fecha_recibo,
                car.estado,
                car.status_recibo,
                car.tipo,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                ci.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre
            FROM cuentas_a_recibir car
            LEFT JOIN tipos_documentos td ON car.documento_id = td.id
            LEFT JOIN bancos b ON car.banco_id = b.id
            LEFT JOIN categorias_ingresos ci ON car.cuenta_id = ci.id
            LEFT JOIN proyectos p ON car.proyecto_id = p.id
            {where_sql}
            ORDER BY car.fecha_emision DESC, car.id DESC
            {limit_sql}
        """
        
        cur.execute(query, params)
        cuentas_a_recibir = cur.fetchall()
        
        # Procesar cuentas a recibir
        for cuenta in cuentas_a_recibir:
            fecha_emision = cuenta['fecha_emision']
            if isinstance(fecha_emision, str):
                fecha_emision = datetime.strptime(fecha_emision, "%Y-%m-%d").date()
            elif isinstance(fecha_emision, datetime):
                fecha_emision = fecha_emision.date()
            
            fecha_vencimiento = cuenta['vencimiento']
            if fecha_vencimiento:
                if isinstance(fecha_vencimiento, str):
                    fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
                elif isinstance(fecha_vencimiento, datetime):
                    fecha_vencimiento = fecha_vencimiento.date()
            
            fecha_recibo = cuenta['fecha_recibo']
            if fecha_recibo:
                if isinstance(fecha_recibo, str):
                    fecha_recibo = datetime.strptime(fecha_recibo, "%Y-%m-%d").date()
                elif isinstance(fecha_recibo, datetime):
                    fecha_recibo = fecha_recibo.date()
            
            # Calcular días de atraso
            dias_atraso = 0
            if fecha_vencimiento:
                if fecha_recibo:
                    if fecha_recibo > fecha_vencimiento:
                        dias_atraso = (fecha_recibo - fecha_vencimiento).days
                else:
                    hoy = date.today()
                    if hoy > fecha_vencimiento:
                        dias_atraso = (hoy - fecha_vencimiento).days
            
            # Determinar estado de pago
            estado_pago = cuenta['estado'] or 'ABIERTO'
            if estado_pago == 'RECIBIDO':
                estado_pago = 'Pagado'
            elif estado_pago == 'ABIERTO':
                if fecha_vencimiento:
                    hoy = date.today()
                    if hoy > fecha_vencimiento:
                        estado_pago = 'Atrasado'
                    elif hoy == fecha_vencimiento:
                        estado_pago = 'En día'
                    else:
                        estado_pago = 'Pendiente'
                else:
                    estado_pago = 'Pendiente'
            
            # Usar status_recibo si está disponible
            if cuenta['status_recibo']:
                status_map = {
                    'ADELANTADO': 'Adelantado',
                    'ATRASADO': 'Atrasado',
                    'EN DIA': 'En día'
                }
                estado_pago = status_map.get(cuenta['status_recibo'], estado_pago)
            
            # Calcular saldo: (valor_cuota o valor) - monto_abonado
            valor_cuota = float(cuenta['valor_cuota']) if cuenta['valor_cuota'] else None
            valor = float(cuenta['valor']) if cuenta['valor'] else 0
            monto_abonado = float(cuenta.get('monto_abonado') or 0)
            monto_comparar = valor_cuota if valor_cuota is not None else valor
            
            # Calcular saldo correctamente
            # El saldo es la diferencia entre lo que se debe y lo que se ha abonado
            if monto_comparar is not None:
                # Para valores positivos: saldo = valor - monto_abonado
                # Para valores negativos (NCRE): el monto_abonado se guarda como positivo,
                # pero conceptualmente es negativo, entonces: saldo = valor + monto_abonado
                if monto_comparar < 0:
                    # NCRE: el valor es negativo, el monto_abonado es positivo pero conceptualmente negativo
                    saldo = monto_comparar + monto_abonado
                    # Si el saldo es positivo (se pagó de más), poner 0
                    if saldo > 0:
                        saldo = 0
                else:
                    # Valor positivo: saldo = valor - monto_abonado
                    saldo = monto_comparar - monto_abonado
                    # Si el saldo queda negativo (se pagó de más), poner 0
                    if saldo < 0:
                        saldo = 0
            else:
                saldo = 0
            
            reporte = {
                'tipo': 'CUENTA_A_RECIBIR',
                'id': cuenta['id'],
                'numero_factura': cuenta['factura'] or f"CAR-{cuenta['id']}",
                'fecha_emision': fecha_emision,
                'cliente': cuenta['cliente'],
                'ruc': None,
                'moneda': 'Gs',
                'tipo_venta': cuenta.get('tipo', 'FCON'),
                'plazo_dias': None,
                'fecha_vencimiento': fecha_vencimiento,
                'fecha_pago': fecha_recibo,
                'estado_pago': estado_pago,
                'dias_atraso': dias_atraso,
                'monto': saldo,  # Mostrar saldo en lugar del monto total
                # Campos adicionales
                'documento_nombre': cuenta.get('documento_nombre'),
                'banco_nombre': cuenta.get('banco_nombre'),
                'cuenta_nombre': cuenta.get('cuenta_nombre'),
                'proyecto_nombre': cuenta.get('proyecto_nombre'),
                'descripcion': cuenta.get('descripcion'),
                'cuotas': cuenta.get('cuotas'),
                'valor_cuota': float(cuenta['valor_cuota']) if cuenta['valor_cuota'] else None
            }
            
            reportes.append(reporte)
        
        # Ordenar por fecha de emisión descendente
        reportes.sort(key=lambda x: x['fecha_emision'] if x['fecha_emision'] else date.min, reverse=True)
        
        return reportes
    finally:
        cur.close()
        conn.close()


def obtener_clientes_con_cuentas_a_recibir():
    """Obtiene lista de clientes que tienen cuentas a recibir"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT DISTINCT cliente, NULL as ruc
            FROM cuentas_a_recibir
            WHERE cliente IS NOT NULL
            ORDER BY cliente
        """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA DASHBOARD DE ANÁLISIS ====================

def obtener_saldos_bancos():
    """Obtiene los saldos actuales de todos los bancos
    
    El saldo se calcula como:
    saldo_actual = saldo_inicial 
                   + entradas (monto_abonado de cuentas_a_recibir con fecha_recibo) 
                   - salidas (monto_abonado de cuentas_a_pagar con fecha_pago)
                   + transferencias recibidas (como destino)
                   - transferencias enviadas (como origen)
    """
    conn, cur = conectar()
    try:
        # Asegurar que la tabla de transferencias existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transferencias_cuentas (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL,
                banco_origen_id INTEGER NOT NULL REFERENCES bancos(id),
                banco_destino_id INTEGER NOT NULL REFERENCES bancos(id),
                monto NUMERIC(15, 2) NOT NULL,
                descripcion TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT banco_origen_destino_diferentes CHECK (banco_origen_id != banco_destino_id),
                CONSTRAINT monto_positivo CHECK (monto > 0)
            );
        """)
        conn.commit()
        
        cur.execute("""
            SELECT 
                b.id,
                b.nombre,
                COALESCE(b.saldo_inicial, 0) as saldo_inicial,
                COALESCE((
                    SELECT SUM(COALESCE(car.monto_abonado, 0))
                    FROM cuentas_a_recibir car
                    WHERE car.banco_id = b.id 
                    AND car.fecha_recibo IS NOT NULL
                ), 0) as entradas,
                COALESCE((
                    SELECT SUM(COALESCE(cap.monto_abonado, 0))
                    FROM cuentas_a_pagar cap
                    WHERE cap.banco_id = b.id 
                    AND cap.fecha_pago IS NOT NULL
                ), 0) as salidas,
                COALESCE((
                    SELECT SUM(COALESCE(t.monto, 0))
                    FROM transferencias_cuentas t
                    WHERE t.banco_destino_id = b.id
                ), 0) as transferencias_recibidas,
                COALESCE((
                    SELECT SUM(COALESCE(t.monto, 0))
                    FROM transferencias_cuentas t
                    WHERE t.banco_origen_id = b.id
                ), 0) as transferencias_enviadas,
                (COALESCE(b.saldo_inicial, 0) + 
                 COALESCE((
                     SELECT SUM(COALESCE(car.monto_abonado, 0))
                     FROM cuentas_a_recibir car
                     WHERE car.banco_id = b.id 
                     AND car.fecha_recibo IS NOT NULL
                 ), 0) - 
                 COALESCE((
                     SELECT SUM(COALESCE(cap.monto_abonado, 0))
                     FROM cuentas_a_pagar cap
                     WHERE cap.banco_id = b.id 
                     AND cap.fecha_pago IS NOT NULL
                 ), 0) +
                 COALESCE((
                     SELECT SUM(COALESCE(t.monto, 0))
                     FROM transferencias_cuentas t
                     WHERE t.banco_destino_id = b.id
                 ), 0) -
                 COALESCE((
                     SELECT SUM(COALESCE(t.monto, 0))
                     FROM transferencias_cuentas t
                     WHERE t.banco_origen_id = b.id
                 ), 0)) as saldo_actual
            FROM bancos b
            WHERE b.activo = true
            ORDER BY b.nombre
        """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_receita_bruta_mensual(ano=None, proyecto_id=None, fecha_desde=None, fecha_hasta=None, tipo_reporte='realizado'):
    """Obtiene la receita bruta mensual (suma de cuentas a recibir)
    
    Args:
        tipo_reporte: 'proyectado' usa valor_cuota (o valor si es NULL), 'realizado' usa monto_abonado
        Usa fecha_recibo para agrupar por mes (régimen de competencia)
    """
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        # Usar fecha_recibo para los filtros y agrupación (régimen de competencia)
        if ano:
            where_clauses.append("EXTRACT(YEAR FROM COALESCE(car.fecha_recibo, car.fecha_emision)) = %s")
            params.append(ano)
        
        if proyecto_id:
            where_clauses.append("car.proyecto_id = %s")
            params.append(proyecto_id)
        
        if fecha_desde:
            where_clauses.append("COALESCE(car.fecha_recibo, car.fecha_emision) >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("COALESCE(car.fecha_recibo, car.fecha_emision) <= %s")
            params.append(fecha_hasta)
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Determinar qué columna usar según el tipo de reporte
        if tipo_reporte == 'proyectado':
            # Proyectado: usar valor_cuota o valor si valor_cuota es NULL
            campo_valor = "COALESCE(car.valor_cuota, car.valor, 0)"
        else:
            # Realizado: usar monto_abonado
            campo_valor = "COALESCE(car.monto_abonado, 0)"
        
        query = f"""
            SELECT 
                EXTRACT(MONTH FROM COALESCE(car.fecha_recibo, car.fecha_emision)) as mes,
                EXTRACT(YEAR FROM COALESCE(car.fecha_recibo, car.fecha_emision)) as ano,
                SUM({campo_valor}) as receita_bruta
            FROM cuentas_a_recibir car
            {where_sql}
            GROUP BY EXTRACT(MONTH FROM COALESCE(car.fecha_recibo, car.fecha_emision)), EXTRACT(YEAR FROM COALESCE(car.fecha_recibo, car.fecha_emision))
            ORDER BY ano, mes
        """
        
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_custos_despesas_mensual(ano=None, proyecto_id=None, fecha_desde=None, fecha_hasta=None, tipo_reporte='realizado'):
    """Obtiene los custos e despesas mensuales (suma de cuentas a pagar)
    
    Args:
        tipo_reporte: 'proyectado' usa valor_cuota (o valor si es NULL), 'realizado' usa monto_abonado
        Usa fecha_pago para agrupar por mes (régimen de competencia)
    """
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        # Usar fecha_pago para los filtros y agrupación (régimen de competencia)
        if ano:
            where_clauses.append("EXTRACT(YEAR FROM COALESCE(cap.fecha_pago, cap.fecha_emision)) = %s")
            params.append(ano)
        
        if proyecto_id:
            where_clauses.append("cap.proyecto_id = %s")
            params.append(proyecto_id)
        
        if fecha_desde:
            where_clauses.append("COALESCE(cap.fecha_pago, cap.fecha_emision) >= %s")
            params.append(fecha_desde)
        
        if fecha_hasta:
            where_clauses.append("COALESCE(cap.fecha_pago, cap.fecha_emision) <= %s")
            params.append(fecha_hasta)
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Determinar qué columna usar según el tipo de reporte
        if tipo_reporte == 'proyectado':
            # Proyectado: usar valor_cuota o valor si valor_cuota es NULL
            campo_valor = "COALESCE(cap.valor_cuota, cap.valor, 0)"
        else:
            # Realizado: usar monto_abonado
            campo_valor = "COALESCE(cap.monto_abonado, 0)"
        
        query = f"""
            SELECT 
                EXTRACT(MONTH FROM COALESCE(cap.fecha_pago, cap.fecha_emision)) as mes,
                EXTRACT(YEAR FROM COALESCE(cap.fecha_pago, cap.fecha_emision)) as ano,
                SUM({campo_valor}) as custos_despesas
            FROM cuentas_a_pagar cap
            {where_sql}
            GROUP BY EXTRACT(MONTH FROM COALESCE(cap.fecha_pago, cap.fecha_emision)), EXTRACT(YEAR FROM COALESCE(cap.fecha_pago, cap.fecha_emision))
            ORDER BY ano, mes
        """
        
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_flujo_caja_mensual(ano=None, proyecto_id=None, fecha_desde=None, fecha_hasta=None):
    """Obtiene el flujo de caja mensual (entradas - salidas)"""
    conn, cur = conectar()
    try:
        where_entradas = []
        where_salidas = []
        params_entradas = []
        params_salidas = []
        
        if ano:
            where_entradas.append("EXTRACT(YEAR FROM car.fecha_recibo) = %s")
            where_salidas.append("EXTRACT(YEAR FROM cap.fecha_pago) = %s")
            params_entradas.append(ano)
            params_salidas.append(ano)
        
        if proyecto_id:
            where_entradas.append("car.proyecto_id = %s")
            where_salidas.append("cap.proyecto_id = %s")
            params_entradas.append(proyecto_id)
            params_salidas.append(proyecto_id)
        
        if fecha_desde:
            where_entradas.append("car.fecha_recibo >= %s")
            where_salidas.append("cap.fecha_pago >= %s")
            params_entradas.append(fecha_desde)
            params_salidas.append(fecha_desde)
        
        if fecha_hasta:
            where_entradas.append("car.fecha_recibo <= %s")
            where_salidas.append("cap.fecha_pago <= %s")
            params_entradas.append(fecha_hasta)
            params_salidas.append(fecha_hasta)
        
        where_sql_entradas = ""
        if where_entradas:
            where_sql_entradas = "AND " + " AND ".join(where_entradas)
        
        where_sql_salidas = ""
        if where_salidas:
            where_sql_salidas = "AND " + " AND ".join(where_salidas)
        
        # Entradas (cuentas a recibir - monto abonado)
        query_entradas = f"""
            SELECT 
                EXTRACT(MONTH FROM car.fecha_recibo) as mes,
                EXTRACT(YEAR FROM car.fecha_recibo) as ano,
                SUM(COALESCE(car.monto_abonado, 0)) as entradas
            FROM cuentas_a_recibir car
            WHERE car.fecha_recibo IS NOT NULL
            {where_sql_entradas}
            GROUP BY EXTRACT(MONTH FROM car.fecha_recibo), EXTRACT(YEAR FROM car.fecha_recibo)
        """
        
        # Salidas (cuentas a pagar - monto abonado)
        query_salidas = f"""
            SELECT 
                EXTRACT(MONTH FROM cap.fecha_pago) as mes,
                EXTRACT(YEAR FROM cap.fecha_pago) as ano,
                SUM(COALESCE(cap.monto_abonado, 0)) as salidas
            FROM cuentas_a_pagar cap
            WHERE cap.fecha_pago IS NOT NULL
            {where_sql_salidas}
            GROUP BY EXTRACT(MONTH FROM cap.fecha_pago), EXTRACT(YEAR FROM cap.fecha_pago)
        """
        
        cur.execute(query_entradas, params_entradas)
        entradas = {f"{int(r['ano'])}-{int(r['mes'])}": float(r['entradas']) for r in cur.fetchall()}
        
        cur.execute(query_salidas, params_salidas)
        salidas = {f"{int(r['ano'])}-{int(r['mes'])}": float(r['salidas']) for r in cur.fetchall()}
        
        # Combinar datos
        todos_meses = set(list(entradas.keys()) + list(salidas.keys()))
        resultado = []
        for mes_key in sorted(todos_meses):
            ano_val, mes_val = mes_key.split('-')
            resultado.append({
                'ano': int(ano_val),
                'mes': int(mes_val),
                'entradas': entradas.get(mes_key, 0),
                'salidas': salidas.get(mes_key, 0)
            })
        
        return resultado
    finally:
        cur.close()
        conn.close()


def obtener_evolucion_saldo_mensual(banco_id=None, ano=None, fecha_desde=None, fecha_hasta=None):
    """Obtiene la evolución del saldo mensual de los bancos"""
    conn, cur = conectar()
    try:
        # Obtener saldo inicial total
        query_saldos_iniciales = """
            SELECT SUM(COALESCE(saldo_inicial, 0)) as saldo_inicial_total
            FROM bancos
            WHERE activo = true
        """
        if banco_id:
            query_saldos_iniciales = """
                SELECT COALESCE(saldo_inicial, 0) as saldo_inicial_total
                FROM bancos
                WHERE id = %s AND activo = true
            """
            cur.execute(query_saldos_iniciales, (banco_id,))
        else:
            cur.execute(query_saldos_iniciales)
        
        saldo_inicial_total = float(cur.fetchone()['saldo_inicial_total'] or 0)
        
        # Construir filtros
        where_entradas = []
        where_salidas = []
        params_entradas = []
        params_salidas = []
        
        if banco_id:
            where_entradas.append("car.banco_id = %s")
            where_salidas.append("cap.banco_id = %s")
            params_entradas.append(banco_id)
            params_salidas.append(banco_id)
        
        if ano:
            where_entradas.append("EXTRACT(YEAR FROM car.fecha_recibo) = %s")
            where_salidas.append("EXTRACT(YEAR FROM cap.fecha_pago) = %s")
            params_entradas.append(ano)
            params_salidas.append(ano)
        
        if fecha_desde:
            where_entradas.append("car.fecha_recibo >= %s")
            where_salidas.append("cap.fecha_pago >= %s")
            params_entradas.append(fecha_desde)
            params_salidas.append(fecha_desde)
        
        if fecha_hasta:
            where_entradas.append("car.fecha_recibo <= %s")
            where_salidas.append("cap.fecha_pago <= %s")
            params_entradas.append(fecha_hasta)
            params_salidas.append(fecha_hasta)
        
        where_sql_entradas = ""
        if where_entradas:
            where_sql_entradas = "AND " + " AND ".join(where_entradas)
        
        where_sql_salidas = ""
        if where_salidas:
            where_sql_salidas = "AND " + " AND ".join(where_salidas)
        
        # Obtener entradas mensuales
        query_entradas = f"""
            SELECT 
                EXTRACT(MONTH FROM car.fecha_recibo) as mes,
                EXTRACT(YEAR FROM car.fecha_recibo) as ano,
                SUM(COALESCE(car.monto_abonado, 0)) as entradas
            FROM cuentas_a_recibir car
            WHERE car.fecha_recibo IS NOT NULL
            {where_sql_entradas}
            GROUP BY EXTRACT(MONTH FROM car.fecha_recibo), EXTRACT(YEAR FROM car.fecha_recibo)
        """
        
        # Obtener salidas mensuales
        query_salidas = f"""
            SELECT 
                EXTRACT(MONTH FROM cap.fecha_pago) as mes,
                EXTRACT(YEAR FROM cap.fecha_pago) as ano,
                SUM(COALESCE(cap.monto_abonado, 0)) as salidas
            FROM cuentas_a_pagar cap
            WHERE cap.fecha_pago IS NOT NULL
            {where_sql_salidas}
            GROUP BY EXTRACT(MONTH FROM cap.fecha_pago), EXTRACT(YEAR FROM cap.fecha_pago)
        """
        
        cur.execute(query_entradas, params_entradas)
        entradas_mes = {f"{int(r['ano'])}-{int(r['mes'])}": float(r['entradas']) for r in cur.fetchall()}
        
        cur.execute(query_salidas, params_salidas)
        salidas_mes = {f"{int(r['ano'])}-{int(r['mes'])}": float(r['salidas']) for r in cur.fetchall()}
        
        # Calcular saldos acumulados
        todos_meses = sorted(set(list(entradas_mes.keys()) + list(salidas_mes.keys())))
        resultado = []
        saldo_acumulado = saldo_inicial_total
        
        for mes_key in todos_meses:
            ano_val, mes_val = mes_key.split('-')
            entradas = entradas_mes.get(mes_key, 0)
            salidas = salidas_mes.get(mes_key, 0)
            saldo_acumulado += entradas - salidas
            
            resultado.append({
                'ano': int(ano_val),
                'mes': int(mes_val),
                'saldo': saldo_acumulado
            })
        
        return resultado
    finally:
        cur.close()
        conn.close()


def obtener_conciliacion_bancaria(banco_id, anio, mes):
    """Obtiene la conciliación bancaria diaria para un banco, año y mes específicos
    
    Retorna:
    - diccionario con banco_id, banco_nombre, saldo_mes_anterior, movimientos
    """
    from calendar import monthrange
    conn, cur = conectar()
    try:
        # Asegurar que la tabla de transferencias existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transferencias_cuentas (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL,
                banco_origen_id INTEGER NOT NULL REFERENCES bancos(id),
                banco_destino_id INTEGER NOT NULL REFERENCES bancos(id),
                monto NUMERIC(15, 2) NOT NULL,
                descripcion TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT banco_origen_destino_diferentes CHECK (banco_origen_id != banco_destino_id),
                CONSTRAINT monto_positivo CHECK (monto > 0)
            );
        """)
        conn.commit()
        
        # Obtener información del banco
        cur.execute("""
            SELECT id, nombre, COALESCE(saldo_inicial, 0) as saldo_inicial
            FROM bancos
            WHERE id = %s AND activo = true
        """, (banco_id,))
        banco = cur.fetchone()
        
        if not banco:
            return None
        
        # Calcular el último día del mes anterior
        if mes == 1:
            mes_anterior = 12
            anio_anterior = anio - 1
        else:
            mes_anterior = mes - 1
            anio_anterior = anio
        
        # Obtener el último día del mes anterior
        ultimo_dia_mes_anterior = monthrange(anio_anterior, mes_anterior)[1]
        fecha_fin_mes_anterior = date(anio_anterior, mes_anterior, ultimo_dia_mes_anterior)
        
        # Calcular saldo acumulado al final del mes anterior
        cur.execute("""
            SELECT 
                COALESCE(b.saldo_inicial, 0) +
                COALESCE((
                    SELECT SUM(COALESCE(car.monto_abonado, 0))
                    FROM cuentas_a_recibir car
                    WHERE car.banco_id = b.id 
                    AND car.fecha_recibo IS NOT NULL
                    AND car.fecha_recibo <= %s
                ), 0) - 
                COALESCE((
                    SELECT SUM(COALESCE(cap.monto_abonado, 0))
                    FROM cuentas_a_pagar cap
                    WHERE cap.banco_id = b.id 
                    AND cap.fecha_pago IS NOT NULL
                    AND cap.fecha_pago <= %s
                ), 0) +
                COALESCE((
                    SELECT SUM(COALESCE(t.monto, 0))
                    FROM transferencias_cuentas t
                    WHERE t.banco_destino_id = b.id
                    AND t.fecha <= %s
                ), 0) -
                COALESCE((
                    SELECT SUM(COALESCE(t.monto, 0))
                    FROM transferencias_cuentas t
                    WHERE t.banco_origen_id = b.id
                    AND t.fecha <= %s
                ), 0) as saldo_acumulado
            FROM bancos b
            WHERE b.id = %s
        """, (fecha_fin_mes_anterior, fecha_fin_mes_anterior, fecha_fin_mes_anterior, fecha_fin_mes_anterior, banco_id))
        
        saldo_mes_anterior = cur.fetchone()['saldo_acumulado'] or 0
        
        # Obtener el número de días del mes
        ultimo_dia_mes = monthrange(anio, mes)[1]
        
        # Generar lista de días del mes
        movimientos = []
        saldo_acumulado = float(saldo_mes_anterior)
        
        for dia in range(1, ultimo_dia_mes + 1):
            fecha_actual = date(anio, mes, dia)
            
            # Ingresos del día (cuentas a recibir)
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(monto_abonado, 0)), 0) as total
                FROM cuentas_a_recibir
                WHERE banco_id = %s
                AND fecha_recibo = %s
            """, (banco_id, fecha_actual))
            ingresos_cuentas = float(cur.fetchone()['total'] or 0)
            
            # Salidas del día (cuentas a pagar)
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(monto_abonado, 0)), 0) as total
                FROM cuentas_a_pagar
                WHERE banco_id = %s
                AND fecha_pago = %s
            """, (banco_id, fecha_actual))
            salidas_cuentas = float(cur.fetchone()['total'] or 0)
            
            # Transferencias recibidas del día (entradas)
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(monto, 0)), 0) as total
                FROM transferencias_cuentas
                WHERE banco_destino_id = %s
                AND fecha = %s
            """, (banco_id, fecha_actual))
            transferencias_recibidas = float(cur.fetchone()['total'] or 0)
            
            # Transferencias enviadas del día (salidas)
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(monto, 0)), 0) as total
                FROM transferencias_cuentas
                WHERE banco_origen_id = %s
                AND fecha = %s
            """, (banco_id, fecha_actual))
            transferencias_enviadas = float(cur.fetchone()['total'] or 0)
            
            # Sumar transferencias a ingresos y salidas
            ingresos = ingresos_cuentas + transferencias_recibidas
            salidas = salidas_cuentas + transferencias_enviadas
            
            # Calcular saldo del día
            saldo_dia = ingresos - salidas
            
            # Actualizar saldo acumulado
            saldo_acumulado += saldo_dia
            
            # Solo agregar si hay movimientos o es el primer día
            if ingresos > 0 or salidas > 0 or dia == 1:
                movimientos.append({
                    'fecha': fecha_actual,
                    'ingresos': ingresos,
                    'salidas': salidas,
                    'saldo_dia': saldo_dia,
                    'saldo_acumulado': saldo_acumulado
                })
        
        return {
            'banco_id': banco_id,
            'banco_nombre': banco['nombre'],
            'saldo_mes_anterior': float(saldo_mes_anterior),
            'movimientos': movimientos
        }
    finally:
        cur.close()
        conn.close()


def obtener_flujo_caja_mensual_detallado(ano=None, proyecto_id=None, tipo_reporte='realizado'):
    """Obtiene el flujo de caja mensual detallado por categorías
    
    Args:
        tipo_reporte: 'proyectado' usa valor_cuota, 'realizado' usa monto_abonado
    """
    from calendar import monthrange
    conn, cur = conectar()
    try:
        # Obtener todas las categorías de ingresos y gastos
        cur.execute("""
            SELECT id, nombre, codigo
            FROM categorias_ingresos
            WHERE activo = true
            ORDER BY orden, codigo
        """)
        categorias_ingresos = cur.fetchall()
        
        cur.execute("""
            SELECT id, nombre, codigo
            FROM categorias_gastos
            WHERE activo = true
            ORDER BY orden, codigo
        """)
        categorias_gastos = cur.fetchall()
        
        # Construir filtros
        where_clauses_ingresos = []
        where_clauses_gastos = []
        params_ingresos = []
        params_gastos = []
        
        if ano:
            if tipo_reporte == 'proyectado':
                where_clauses_ingresos.append("EXTRACT(YEAR FROM car.fecha_emision) = %s")
                where_clauses_gastos.append("EXTRACT(YEAR FROM cap.fecha_emision) = %s")
            else:
                where_clauses_ingresos.append("EXTRACT(YEAR FROM car.fecha_recibo) = %s")
                where_clauses_gastos.append("EXTRACT(YEAR FROM cap.fecha_pago) = %s")
            params_ingresos.append(ano)
            params_gastos.append(ano)
        
        if proyecto_id:
            where_clauses_ingresos.append("car.proyecto_id = %s")
            where_clauses_gastos.append("cap.proyecto_id = %s")
            params_ingresos.append(proyecto_id)
            params_gastos.append(proyecto_id)
        
        where_sql_ingresos = ""
        if where_clauses_ingresos:
            where_sql_ingresos = "AND " + " AND ".join(where_clauses_ingresos)
        
        where_sql_gastos = ""
        if where_clauses_gastos:
            where_sql_gastos = "AND " + " AND ".join(where_clauses_gastos)
        
        # Determinar qué columna usar según el tipo de reporte
        if tipo_reporte == 'proyectado':
            campo_ingresos = "COALESCE(car.valor_cuota, car.valor, 0)"
            campo_gastos = "COALESCE(cap.valor_cuota, cap.valor, 0)"
            fecha_ingresos = "car.fecha_emision"
            fecha_gastos = "cap.fecha_emision"
        else:
            campo_ingresos = "COALESCE(car.monto_abonado, 0)"
            campo_gastos = "COALESCE(cap.monto_abonado, 0)"
            fecha_ingresos = "car.fecha_recibo"
            fecha_gastos = "cap.fecha_pago"
            where_sql_ingresos += " AND car.fecha_recibo IS NOT NULL"
            where_sql_gastos += " AND cap.fecha_pago IS NOT NULL"
        
        # Obtener ingresos por categoría y mes
        ingresos_por_categoria = {}
        for cat in categorias_ingresos:
            query = f"""
                SELECT 
                    EXTRACT(MONTH FROM {fecha_ingresos}) as mes,
                    EXTRACT(YEAR FROM {fecha_ingresos}) as ano,
                    SUM({campo_ingresos}) as total
                FROM cuentas_a_recibir car
                WHERE car.cuenta_id = %s
                {where_sql_ingresos}
                GROUP BY EXTRACT(MONTH FROM {fecha_ingresos}), EXTRACT(YEAR FROM {fecha_ingresos})
            """
            cur.execute(query, [cat['id']] + params_ingresos)
            ingresos_por_categoria[cat['id']] = {
                f"{int(r['ano'])}-{int(r['mes'])}": float(r['total']) 
                for r in cur.fetchall()
            }
        
        # Obtener gastos por categoría y mes
        gastos_por_categoria = {}
        for cat in categorias_gastos:
            query = f"""
                SELECT 
                    EXTRACT(MONTH FROM {fecha_gastos}) as mes,
                    EXTRACT(YEAR FROM {fecha_gastos}) as ano,
                    SUM({campo_gastos}) as total
                FROM cuentas_a_pagar cap
                WHERE cap.cuenta_id = %s
                {where_sql_gastos}
                GROUP BY EXTRACT(MONTH FROM {fecha_gastos}), EXTRACT(YEAR FROM {fecha_gastos})
            """
            cur.execute(query, [cat['id']] + params_gastos)
            gastos_por_categoria[cat['id']] = {
                f"{int(r['ano'])}-{int(r['mes'])}": float(r['total']) 
                for r in cur.fetchall()
            }
        
        # Obtener saldo inicial total de bancos
        cur.execute("""
            SELECT SUM(COALESCE(saldo_inicial, 0)) as saldo_inicial_total
            FROM bancos
            WHERE activo = true
        """)
        saldo_inicial_total = float(cur.fetchone()['saldo_inicial_total'] or 0)
        
        # Obtener movimientos anteriores al año seleccionado para calcular saldo inicial
        if ano:
            fecha_inicio_ano = date(ano, 1, 1)
            
            # Entradas anteriores
            if tipo_reporte == 'realizado':
                cur.execute("""
                    SELECT SUM(COALESCE(monto_abonado, 0)) as total
                    FROM cuentas_a_recibir
                    WHERE fecha_recibo IS NOT NULL AND fecha_recibo < %s
                """, (fecha_inicio_ano,))
            else:
                cur.execute("""
                    SELECT SUM(COALESCE(valor_cuota, valor, 0)) as total
                    FROM cuentas_a_recibir
                    WHERE fecha_emision < %s
                """, (fecha_inicio_ano,))
            entradas_anteriores = float(cur.fetchone()['total'] or 0)
            
            # Salidas anteriores
            if tipo_reporte == 'realizado':
                cur.execute("""
                    SELECT SUM(COALESCE(monto_abonado, 0)) as total
                    FROM cuentas_a_pagar
                    WHERE fecha_pago IS NOT NULL AND fecha_pago < %s
                """, (fecha_inicio_ano,))
            else:
                cur.execute("""
                    SELECT SUM(COALESCE(valor_cuota, valor, 0)) as total
                    FROM cuentas_a_pagar
                    WHERE fecha_emision < %s
                """, (fecha_inicio_ano,))
            salidas_anteriores = float(cur.fetchone()['total'] or 0)
            
            saldo_inicial_enero = saldo_inicial_total + entradas_anteriores - salidas_anteriores
        else:
            saldo_inicial_enero = saldo_inicial_total
        
        # Construir estructura de datos por mes
        meses_nombres = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 
                        'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
        
        resultado = {
            'ano': ano,
            'proyecto_id': proyecto_id,
            'tipo_reporte': tipo_reporte,
            'categorias_ingresos': [{'id': c['id'], 'nombre': c['nombre']} for c in categorias_ingresos],
            'categorias_gastos': [{'id': c['id'], 'nombre': c['nombre']} for c in categorias_gastos],
            'meses': []
        }
        
        saldo_actual = saldo_inicial_enero
        
        for mes in range(1, 13):
            mes_key = f"{ano}-{mes}" if ano else None
            mes_nombre = meses_nombres[mes - 1]
            
            # Calcular saldo inicial del mes (saldo final del mes anterior)
            saldo_inicial_mes = saldo_actual
            
            # Total de ingresos del mes
            total_ingresos = 0
            ingresos_categoria = {}
            for cat in categorias_ingresos:
                valor = ingresos_por_categoria.get(cat['id'], {}).get(mes_key, 0)
                ingresos_categoria[cat['id']] = valor
                total_ingresos += valor
            
            # Total de gastos del mes
            total_gastos = 0
            gastos_categoria = {}
            for cat in categorias_gastos:
                valor = gastos_por_categoria.get(cat['id'], {}).get(mes_key, 0)
                gastos_categoria[cat['id']] = valor
                total_gastos += valor
            
            # Saldo operacional
            saldo_operacional = total_ingresos - total_gastos
            
            # Saldo final
            saldo_final = saldo_inicial_mes + total_ingresos - total_gastos
            saldo_actual = saldo_final
            
            resultado['meses'].append({
                'mes': mes,
                'mes_nombre': mes_nombre,
                'saldo_inicial': saldo_inicial_mes,
                'total_ingresos': total_ingresos,
                'ingresos_categoria': ingresos_categoria,
                'total_gastos': total_gastos,
                'gastos_categoria': gastos_categoria,
                'saldo_operacional': saldo_operacional,
                'saldo_final': saldo_final
            })
        
        return resultado
    finally:
        cur.close()
        conn.close()


def obtener_dre_mensual(ano=None, proyecto_id=None, tipo_reporte='realizado'):
    """Obtiene el DRE (Demonstrativo de Resultado) mensual
    
    Args:
        tipo_reporte: 'proyectado' usa valor_cuota, 'realizado' usa monto_abonado
    """
    conn, cur = conectar()
    try:
        # Obtener todas las categorías de ingresos y gastos
        cur.execute("""
            SELECT id, nombre, codigo
            FROM categorias_ingresos
            WHERE activo = true
            ORDER BY orden, codigo
        """)
        categorias_ingresos = cur.fetchall()
        
        cur.execute("""
            SELECT id, nombre, codigo
            FROM categorias_gastos
            WHERE activo = true
            ORDER BY orden, codigo
        """)
        categorias_gastos = cur.fetchall()
        
        # Identificar categorías especiales por nombre (case insensitive)
        categoria_deducciones_id = None
        categoria_costos_variables_id = None
        categoria_ingresos_financieros_id = None
        categoria_gastos_financieros_id = None
        categoria_impuestos_directos_id = None
        
        for cat in categorias_gastos:
            nombre_upper = cat['nombre'].upper()
            if 'DEDUCCION' in nombre_upper or 'DEDUCCIÓN' in nombre_upper or 'DEDUCCIONES' in nombre_upper:
                categoria_deducciones_id = cat['id']
            elif 'COSTO VARIABLE' in nombre_upper or 'COSTOS VARIABLES' in nombre_upper:
                categoria_costos_variables_id = cat['id']
            elif 'GASTO FINANCIERO' in nombre_upper or 'GASTOS FINANCIEROS' in nombre_upper:
                categoria_gastos_financieros_id = cat['id']
            elif 'IMPUESTO DIRECTO' in nombre_upper or 'IMPUESTOS DIRECTOS' in nombre_upper:
                categoria_impuestos_directos_id = cat['id']
        
        for cat in categorias_ingresos:
            nombre_upper = cat['nombre'].upper()
            if 'INGRESO FINANCIERO' in nombre_upper or 'INGRESOS FINANCIEROS' in nombre_upper:
                categoria_ingresos_financieros_id = cat['id']
        
        # Construir filtros
        where_clauses_ingresos = []
        where_clauses_gastos = []
        params_ingresos = []
        params_gastos = []
        
        if ano:
            if tipo_reporte == 'proyectado':
                where_clauses_ingresos.append("EXTRACT(YEAR FROM car.fecha_emision) = %s")
                where_clauses_gastos.append("EXTRACT(YEAR FROM cap.fecha_emision) = %s")
            else:
                where_clauses_ingresos.append("EXTRACT(YEAR FROM car.fecha_recibo) = %s")
                where_clauses_gastos.append("EXTRACT(YEAR FROM cap.fecha_pago) = %s")
            params_ingresos.append(ano)
            params_gastos.append(ano)
        
        if proyecto_id:
            where_clauses_ingresos.append("car.proyecto_id = %s")
            where_clauses_gastos.append("cap.proyecto_id = %s")
            params_ingresos.append(proyecto_id)
            params_gastos.append(proyecto_id)
        
        where_sql_ingresos = ""
        if where_clauses_ingresos:
            where_sql_ingresos = "AND " + " AND ".join(where_clauses_ingresos)
        
        where_sql_gastos = ""
        if where_clauses_gastos:
            where_sql_gastos = "AND " + " AND ".join(where_clauses_gastos)
        
        # Determinar qué columna usar según el tipo de reporte
        if tipo_reporte == 'proyectado':
            campo_ingresos = "COALESCE(car.valor_cuota, car.valor, 0)"
            campo_gastos = "COALESCE(cap.valor_cuota, cap.valor, 0)"
            fecha_ingresos = "car.fecha_emision"
            fecha_gastos = "cap.fecha_emision"
        else:
            campo_ingresos = "COALESCE(car.monto_abonado, 0)"
            campo_gastos = "COALESCE(cap.monto_abonado, 0)"
            fecha_ingresos = "car.fecha_recibo"
            fecha_gastos = "cap.fecha_pago"
            where_sql_ingresos += " AND car.fecha_recibo IS NOT NULL"
            where_sql_gastos += " AND cap.fecha_pago IS NOT NULL"
        
        # Obtener ingresos por categoría y mes
        ingresos_por_categoria = {}
        for cat in categorias_ingresos:
            query = f"""
                SELECT 
                    EXTRACT(MONTH FROM {fecha_ingresos}) as mes,
                    EXTRACT(YEAR FROM {fecha_ingresos}) as ano,
                    SUM({campo_ingresos}) as total
                FROM cuentas_a_recibir car
                WHERE car.cuenta_id = %s
                {where_sql_ingresos}
                GROUP BY EXTRACT(MONTH FROM {fecha_ingresos}), EXTRACT(YEAR FROM {fecha_ingresos})
            """
            cur.execute(query, [cat['id']] + params_ingresos)
            ingresos_por_categoria[cat['id']] = {
                f"{int(r['ano'])}-{int(r['mes'])}": float(r['total']) 
                for r in cur.fetchall()
            }
        
        # Obtener gastos por categoría y mes
        gastos_por_categoria = {}
        for cat in categorias_gastos:
            query = f"""
                SELECT 
                    EXTRACT(MONTH FROM {fecha_gastos}) as mes,
                    EXTRACT(YEAR FROM {fecha_gastos}) as ano,
                    SUM({campo_gastos}) as total
                FROM cuentas_a_pagar cap
                WHERE cap.cuenta_id = %s
                {where_sql_gastos}
                GROUP BY EXTRACT(MONTH FROM {fecha_gastos}), EXTRACT(YEAR FROM {fecha_gastos})
            """
            cur.execute(query, [cat['id']] + params_gastos)
            gastos_por_categoria[cat['id']] = {
                f"{int(r['ano'])}-{int(r['mes'])}": float(r['total']) 
                for r in cur.fetchall()
            }
        
        # Construir estructura de datos por mes
        meses_nombres = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 
                        'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
        
        resultado = {
            'ano': ano,
            'proyecto_id': proyecto_id,
            'tipo_reporte': tipo_reporte,
            'categorias_ingresos': [{'id': c['id'], 'nombre': c['nombre']} for c in categorias_ingresos],
            'categorias_gastos': [{'id': c['id'], 'nombre': c['nombre']} for c in categorias_gastos],
            'categoria_deducciones_id': categoria_deducciones_id,
            'categoria_costos_variables_id': categoria_costos_variables_id,
            'categoria_ingresos_financieros_id': categoria_ingresos_financieros_id,
            'categoria_gastos_financieros_id': categoria_gastos_financieros_id,
            'categoria_impuestos_directos_id': categoria_impuestos_directos_id,
            'meses': []
        }
        
        for mes in range(1, 13):
            mes_key = f"{ano}-{mes}" if ano else None
            mes_nombre = meses_nombres[mes - 1]
            
            # Receita Bruta (suma de todos los ingresos)
            receita_bruta = 0
            ingresos_categoria = {}
            for cat in categorias_ingresos:
                valor = ingresos_por_categoria.get(cat['id'], {}).get(mes_key, 0)
                ingresos_categoria[cat['id']] = valor
                receita_bruta += valor
            
            # Deducciones sobre Ventas
            deducciones = gastos_por_categoria.get(categoria_deducciones_id, {}).get(mes_key, 0) if categoria_deducciones_id else 0
            
            # Receita Líquida
            receita_liquida = receita_bruta - deducciones
            
            # Costos Variables
            costos_variables = gastos_por_categoria.get(categoria_costos_variables_id, {}).get(mes_key, 0) if categoria_costos_variables_id else 0
            
            # Margem Contribuição
            margem_contribuicao = receita_liquida - costos_variables
            
            # % Margem Contribuição
            percentual_margem_contribuicao = (margem_contribuicao / receita_liquida * 100) if receita_liquida != 0 else 0
            
            # Despesas (todas las categorías de gastos excepto deducciones, costos variables, gastos financieros e impuestos)
            despesas = 0
            gastos_categoria = {}
            for cat in categorias_gastos:
                if cat['id'] not in [categoria_deducciones_id, categoria_costos_variables_id, 
                                     categoria_gastos_financieros_id, categoria_impuestos_directos_id]:
                    valor = gastos_por_categoria.get(cat['id'], {}).get(mes_key, 0)
                    gastos_categoria[cat['id']] = valor
                    despesas += valor
            
            # Lucro Operacional
            lucro_operacional = margem_contribuicao - despesas
            
            # Ingresos Financieros
            ingresos_financieros = ingresos_por_categoria.get(categoria_ingresos_financieros_id, {}).get(mes_key, 0) if categoria_ingresos_financieros_id else 0
            
            # Gastos Financieros
            gastos_financieros = gastos_por_categoria.get(categoria_gastos_financieros_id, {}).get(mes_key, 0) if categoria_gastos_financieros_id else 0
            
            # Resultado Financeiro
            resultado_financeiro = ingresos_financieros - gastos_financieros
            
            # Impuestos Directos
            impuestos_directos = gastos_por_categoria.get(categoria_impuestos_directos_id, {}).get(mes_key, 0) if categoria_impuestos_directos_id else 0
            
            # Lucro Líquido
            lucro_liquido = lucro_operacional + resultado_financeiro - impuestos_directos
            
            # % Margem Líquida
            percentual_margem_liquida = (lucro_liquido / receita_liquida * 100) if receita_liquida != 0 else 0
            
            resultado['meses'].append({
                'mes': mes,
                'mes_nombre': mes_nombre,
                'receita_bruta': receita_bruta,
                'ingresos_categoria': ingresos_categoria,
                'deducciones': deducciones,
                'receita_liquida': receita_liquida,
                'costos_variables': costos_variables,
                'margem_contribuicao': margem_contribuicao,
                'percentual_margem_contribuicao': percentual_margem_contribuicao,
                'despesas': despesas,
                'gastos_categoria': gastos_categoria,
                'lucro_operacional': lucro_operacional,
                'ingresos_financieros': ingresos_financieros,
                'gastos_financieros': gastos_financieros,
                'resultado_financeiro': resultado_financeiro,
                'impuestos_directos': impuestos_directos,
                'lucro_liquido': lucro_liquido,
                'percentual_margem_liquida': percentual_margem_liquida
            })
        
        return resultado
    finally:
        cur.close()
        conn.close()
