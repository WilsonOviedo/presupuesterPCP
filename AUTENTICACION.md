# Sistema de Autenticación y Permisos

Este sistema implementa autenticación de usuarios con control de acceso basado en permisos.

## Características

- **Login de usuarios**: Sistema de autenticación con contraseñas hasheadas
- **Usuario Administrador**: Los administradores tienen acceso a todas las rutas
- **Permisos por ruta**: Los usuarios pueden tener permisos específicos para acceder a ciertas rutas
- **Gestión de usuarios**: Los administradores pueden crear, editar y gestionar usuarios y sus permisos

## Configuración Inicial

### 1. Variables de Entorno

Agrega las siguientes variables a tu archivo `.env`:

```env
SECRET_KEY=tu-clave-secreta-muy-segura-aqui
PASSWORD_SALT=tu-salt-para-contraseñas-aqui
```

**Importante**: Cambia estos valores por valores seguros y únicos en producción.

### 2. Crear Usuario Administrador

Después de ejecutar el esquema SQL (que crea las tablas de usuarios y permisos), crea el primer usuario administrador:

```bash
python crear_usuario_admin.py admin tu_contraseña_segura
```

Ejemplo:
```bash
python crear_usuario_admin.py admin admin123
```

### 3. Iniciar Sesión

1. Accede a la aplicación en `http://localhost:5000`
2. Serás redirigido al login si no estás autenticado
3. Ingresa el usuario y contraseña del administrador
4. Una vez autenticado, tendrás acceso a todas las funcionalidades

## Gestión de Usuarios

### Como Administrador

1. Accede al menú principal
2. Verás una tarjeta "🔐 Gestión de Usuarios" (solo visible para admins)
3. Haz clic en "Gestionar Usuarios"

### Crear Nuevo Usuario

1. En la página de usuarios, haz clic en "+ Nuevo Usuario"
2. Completa el formulario:
   - **Usuario**: Nombre de usuario (único, no se puede cambiar después)
   - **Nombre Completo**: Opcional
   - **Email**: Opcional
   - **Contraseña**: Requerida para nuevos usuarios
   - **Usuario Administrador**: Marca esta casilla si quieres que tenga acceso total
   - **Usuario Activo**: Desmarca para desactivar el usuario sin eliminarlo
3. Haz clic en "Guardar"

### Asignar Permisos

1. En la lista de usuarios, haz clic en "Permisos" junto al usuario
2. Selecciona las rutas a las que el usuario tendrá acceso
3. Los administradores no necesitan permisos específicos (tienen acceso a todo)
4. Haz clic en "Guardar Permisos"

### Editar Usuario

1. En la lista de usuarios, haz clic en "Editar"
2. Puedes cambiar:
   - Nombre completo
   - Email
   - Contraseña (dejar vacío para no cambiar)
   - Estado de administrador
   - Estado activo/inactivo
3. **Nota**: El nombre de usuario no se puede cambiar

## Rutas Protegidas

Las siguientes rutas requieren autenticación y permisos:

- `/precios` - Ver precios
- `/precios/cargar-manual` - Cargar precios manualmente
- `/precios/cargar-proveedores` - Cargar proveedores
- `/leer-facturas` - Leer facturas desde correo
- `/calculadora` - Calculadora de precios
- `/historial` - Historial de precios
- `/listas-materiales` - Gestión de listas de materiales
- `/listas-materiales/clientes` - Gestión de clientes
- `/listas-materiales/items_mano_de_obra` - Gestión de items
- `/listas-materiales/materiales_genericos` - Gestión de materiales genéricos
- `/listas-materiales/marcas` - Gestión de marcas
- `/listas-materiales/prefijos_codigos` - Gestión de prefijos
- `/usuarios` - Gestión de usuarios (solo admin)

## Permisos Predefinidos

El sistema crea automáticamente los siguientes permisos al ejecutar el esquema SQL:

- Ver precios
- Cargar precios manualmente
- Cargar proveedores
- Leer facturas
- Calculadora de precio
- Historial de precios
- Listas de materiales
- Gestión de clientes
- Gestión de items
- Gestión de materiales
- Gestión de materiales genéricos
- Gestión de marcas
- Gestión de prefijos
- Gestión de usuarios

## Seguridad

- Las contraseñas se almacenan como hash SHA-256 con salt
- Las sesiones utilizan una clave secreta configurable
- Los usuarios inactivos no pueden iniciar sesión
- Los administradores tienen acceso completo sin necesidad de permisos específicos

## Solución de Problemas

### No puedo iniciar sesión

1. Verifica que el usuario existe y está activo
2. Verifica que la contraseña es correcta
3. Verifica que las tablas de usuarios se crearon correctamente en la base de datos

### No tengo acceso a una ruta

1. Verifica que estás autenticado (deberías ver tu nombre de usuario en la barra superior)
2. Si no eres administrador, verifica que tienes el permiso asignado
3. Contacta a un administrador para que te asigne los permisos necesarios

### Olvidé la contraseña del administrador

Si olvidaste la contraseña del administrador, puedes crear uno nuevo desde la línea de comandos:

```bash
python crear_usuario_admin.py nuevo_admin nueva_contraseña
```

Luego inicia sesión con el nuevo usuario y cambia la contraseña del usuario anterior desde la interfaz web.

