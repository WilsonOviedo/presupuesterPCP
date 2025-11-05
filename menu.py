import sys


def ejecutar_buscar_precios():
    # Importación diferida para evitar costos al mostrar el menú
    from buscar_precios_web import app
    # Ejecuta el servidor Flask (bloqueante hasta que se detenga)
    app.run(host="127.0.0.1", port=5000, debug=True)


def ejecutar_leer_facturas():
    from leer_factura import procesar_correos
    procesar_correos()


def mostrar_menu():
    print("\n=== Menú Principal ===")
    print("1) Buscar precios (web)")
    print("2) Leer facturas (correo IMAP)")
    print("3) Salir")


def main():
    while True:
        mostrar_menu()
        opcion = input("Seleccione una opción (1-3): ").strip()

        if opcion == "1":
            try:
                ejecutar_buscar_precios()
            except KeyboardInterrupt:
                print("\nServidor detenido por el usuario.")
            except Exception as e:
                print(f"Error al iniciar la web de precios: {e}")
        elif opcion == "2":
            try:
                ejecutar_leer_facturas()
            except Exception as e:
                print(f"Error al leer facturas: {e}")
        elif opcion == "3":
            print("Saliendo...")
            sys.exit(0)
        else:
            print("Opción no válida. Intente nuevamente.")


if __name__ == "__main__":
    main()


