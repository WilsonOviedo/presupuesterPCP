"""
Script para crear el usuario administrador inicial
Uso: python crear_usuario_admin.py [username] [password] [email opcional]
"""
import sys
import os
from dotenv import load_dotenv
import auth

load_dotenv()

def main():
    if len(sys.argv) < 3:
        print("Uso: python crear_usuario_admin.py <username> <password> [email]")
        print("Ejemplo: python crear_usuario_admin.py admin admin123")
        print("Ejemplo: python crear_usuario_admin.py admin admin123 admin@example.com")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    # Email es opcional, si no se proporciona se genera uno automático
    if len(sys.argv) >= 4:
        email = sys.argv[3]
    else:
        # Generar email automático basado en el username
        email = f"{username}@localhost"
    
    print(f"Creando usuario administrador: {username}")
    print(f"Email: {email}")
    
    usuario_id = auth.crear_usuario(
        username=username,
        password=password,
        nombre_completo="Administrador",
        email=email,
        es_admin=True
    )
    
    if usuario_id:
        print(f"✅ Usuario administrador '{username}' creado correctamente (ID: {usuario_id})")
        print(f"   Puedes iniciar sesión con este usuario para gestionar otros usuarios y permisos.")
    else:
        print(f"❌ Error al crear usuario. Puede que el usuario ya exista.")
        sys.exit(1)

if __name__ == "__main__":
    main()

