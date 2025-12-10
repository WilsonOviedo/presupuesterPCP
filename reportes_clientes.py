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


def obtener_reportes_cuentas_a_pagar(proveedor_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None):
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
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
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


def obtener_reportes_cuentas_a_recibir(cliente_nombre=None, fecha_desde=None, fecha_hasta=None, estado_pago_filtro=None, tipo_filtro=None):
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
            if estado_pago_filtro == 'pagado':
                where_clauses.append("car.estado = 'RECIBIDO'")
            elif estado_pago_filtro == 'pendiente':
                where_clauses.append("car.estado = 'ABIERTO'")
            elif estado_pago_filtro == 'atrasado':
                where_clauses.append("(car.estado = 'ABIERTO' AND car.vencimiento < CURRENT_DATE) OR car.status_recibo = 'ATRASADO'")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
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

