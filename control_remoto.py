import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ==========================================================
# CONFIGURACIÓN DEL SERVIDOR TCP (PC)
# ==========================================================
HOST = "0.0.0.0"  # Escucha en todas las interfaces de red de la PC
PORT = 8001


class ControlRemotoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Control Remoto RC - Raspberry Pi Pico W")
        self.root.geometry("820x500")
        self.root.configure(bg="#1E1E2E")
        self.root.resizable(False, False)

        # Variables de conexión y estado
        self.client_socket = None
        self.conectado = False
        self.dec_ldr_activo = False
        self.teclas_presionadas = set()

        # Estados de luces para la subventana
        self.estado_lf = False
        self.estado_lb = False
        self.estado_ll = False
        self.estado_lr = False
        self.estado_lboth = False

        self.construir_interfaz()
        self.configurar_teclado()
        self.iniciar_servidor_socket()

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ ESTILO CONTROL REMOTO
    # ==========================================================
    def construir_interfaz(self):
        # --- Barra Superior: Estado de Conexión y Telemetría ---
        top_frame = tk.Frame(self.root, bg="#181825", height=55)
        top_frame.pack(fill="x", padx=15, pady=(12, 8))

        self.lbl_estado = tk.Label(
            top_frame,
            text="● ESPERANDO CONEXIÓN DE RASPBERRY PI PICO W...",
            fg="#F38BA8",
            bg="#181825",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_estado.pack(side="left", padx=15, pady=12)

        self.lbl_telemetria = tk.Label(
            top_frame,
            text="Decrementador: Inactivo",
            fg="#A6ADC8",
            bg="#181825",
            font=("Consolas", 10),
        )
        self.lbl_telemetria.pack(side="right", padx=15, pady=12)

        # --- Cuerpo Principal del Control Remoto (3 Columnas) ---
        cuerpo = tk.Frame(self.root, bg="#252538", bd=3, relief="ridge")
        cuerpo.pack(fill="both", expand=True, padx=15, pady=8)

        # 1. PANEL IZQUIERDO: PALANCA DE TRACCIÓN (AVANZAR / RETROCEDER)
        panel_izq = tk.Frame(cuerpo, bg="#252538", width=230)
        panel_izq.pack(side="left", fill="y", padx=20, pady=20)

        tk.Label(
            panel_izq,
            text="TRACCIÓN",
            fg="#CDD6F4",
            bg="#252538",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(10, 15))

        btn_avanzar = tk.Button(
            panel_izq,
            text="▲\nAVANZAR\n(W / ↑)",
            width=14,
            height=4,
            bg="#313244",
            fg="#A6E3A1",
            activebackground="#45475A",
            font=("Segoe UI", 11, "bold"),
            relief="raised",
            bd=4,
        )
        btn_avanzar.pack(pady=10)
        btn_avanzar.bind("<ButtonPress-1>", lambda e: self.enviar_comando("move 1"))
        btn_avanzar.bind("<ButtonRelease-1>", lambda e: self.enviar_comando("move 0"))

        btn_retroceder = tk.Button(
            panel_izq,
            text="▼\nRETROCEDER\n(S / ↓)",
            width=14,
            height=4,
            bg="#313244",
            fg="#F38BA8",
            activebackground="#45475A",
            font=("Segoe UI", 11, "bold"),
            relief="raised",
            bd=4,
        )
        btn_retroceder.pack(pady=10)
        btn_retroceder.bind("<ButtonPress-1>", lambda e: self.enviar_comando("move -1"))
        btn_retroceder.bind("<ButtonRelease-1>", lambda e: self.enviar_comando("move 0"))

        # 2. PANEL CENTRAL: MODOS, DECREMENTADOR Y VENTANAS AUXILIARES
        panel_centro = tk.Frame(cuerpo, bg="#1E1E2E", bd=2, relief="groove")
        panel_centro.pack(side="left", fill="both", expand=True, padx=10, pady=15)

        tk.Label(
            panel_centro,
            text="MODOS DE RECORRIDO",
            fg="#89B4FA",
            bg="#1E1E2E",
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(10, 5))

        grid_modos = tk.Frame(panel_centro, bg="#1E1E2E")
        grid_modos.pack(pady=5)

        modos = [
            ("Circle", "circle", 0, 0),
            ("Infinite", "infinite", 0, 1),
            ("ZigZag", "zigzag", 1, 0),
            ("Especial", "especial", 1, 1),
        ]
        for texto, cmd, fila, col in modos:
            b = tk.Button(
                grid_modos,
                text=texto,
                width=13,
                height=2,
                bg="#313244",
                fg="#CDD6F4",
                activebackground="#89B4FA",
                font=("Segoe UI", 9, "bold"),
                command=lambda c=cmd: self.enviar_comando(c),
            )
            b.grid(row=fila, column=col, padx=6, pady=5)

        # Control de velocidad PWM
        frame_vel = tk.Frame(panel_centro, bg="#1E1E2E")
        frame_vel.pack(pady=6)
        tk.Label(
            frame_vel,
            text="Potencia Motor:",
            fg="#CDD6F4",
            bg="#1E1E2E",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=5)
        self.scale_vel = tk.Scale(
            frame_vel,
            from_=1,
            to=4,
            orient="horizontal",
            length=120,
            bg="#1E1E2E",
            fg="#CDD6F4",
            highlightthickness=0,
            command=lambda val: self.enviar_comando(f"speed {val}"),
        )
        self.scale_vel.set(4)
        self.scale_vel.pack(side="left")

        ttk.Separator(panel_centro, orient="horizontal").pack(fill="x", padx=15, pady=8)

        # Botón Activar/Desactivar Circuito Decrementador (Fotorresistencia)
        self.btn_dec_auto = tk.Button(
            panel_centro,
            text="Circuito Decrementador (LDR): OFF",
            width=30,
            height=2,
            bg="#45475A",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            command=self.toggle_decrementador_ldr,
        )
        self.btn_dec_auto.pack(pady=5)

        # Fila inferior de botones de subventanas: Luces, Decremento manual y About
        frame_sub = tk.Frame(panel_centro, bg="#1E1E2E")
        frame_sub.pack(pady=8)

        tk.Button(
            frame_sub,
            text="Luces",
            width=10,
            height=2,
            bg="#F9E2AF",
            fg="#1E1E2E",
            font=("Segoe UI", 9, "bold"),
            command=self.abrir_ventana_luces,
        ).grid(row=0, column=0, padx=4)

        tk.Button(
            frame_sub,
            text="Decremento manual",
            width=17,
            height=2,
            bg="#CBA6F7",
            fg="#1E1E2E",
            font=("Segoe UI", 9, "bold"),
            command=self.abrir_ventana_decremento_manual,
        ).grid(row=0, column=1, padx=4)

        tk.Button(
            frame_sub,
            text="About",
            width=7,
            height=2,
            bg="#94E2D5",
            fg="#1E1E2E",
            font=("Segoe UI", 9, "bold"),
            command=self.abrir_ventana_about,
        ).grid(row=0, column=2, padx=4)

        # 3. PANEL DERECHO: PALANCA DE DIRECCIÓN (IZQUIERDA / DERECHA)
        panel_der = tk.Frame(cuerpo, bg="#252538", width=230)
        panel_der.pack(side="right", fill="y", padx=20, pady=20)

        tk.Label(
            panel_der,
            text="DIRECCIÓN (MANTENER)",
            fg="#CDD6F4",
            bg="#252538",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(10, 15))

        frame_giros = tk.Frame(panel_der, bg="#252538")
        frame_giros.pack(pady=35)

        btn_izq = tk.Button(
            frame_giros,
            text="◄\nIZQUIERDA\n(A / ←)",
            width=11,
            height=5,
            bg="#313244",
            fg="#89DCEB",
            activebackground="#45475A",
            font=("Segoe UI", 10, "bold"),
            relief="raised",
            bd=4,
        )
        btn_izq.grid(row=0, column=0, padx=6)
        # El giro inicia al presionar y termina exactamente al soltar
        btn_izq.bind("<ButtonPress-1>", lambda e: self.enviar_comando("turn -1"))
        btn_izq.bind("<ButtonRelease-1>", lambda e: self.enviar_comando("turn 0"))

        btn_der = tk.Button(
            frame_giros,
            text="►\nDERECHA\n(D / →)",
            width=11,
            height=5,
            bg="#313244",
            fg="#89DCEB",
            activebackground="#45475A",
            font=("Segoe UI", 10, "bold"),
            relief="raised",
            bd=4,
        )
        btn_der.grid(row=0, column=1, padx=6)
        btn_der.bind("<ButtonPress-1>", lambda e: self.enviar_comando("turn 1"))
        btn_der.bind("<ButtonRelease-1>", lambda e: self.enviar_comando("turn 0"))

    # ==========================================================
    # CONTROL POR TECLADO (MANTENER PRESIONADO PARA GIRAR/MOVER)
    # ==========================================================
    def configurar_teclado(self):
        self.root.bind("<KeyPress>", self.al_presionar_tecla)
        self.root.bind("<KeyRelease>", self.al_soltar_tecla)

    def al_presionar_tecla(self, event):
        # Ignorar eventos de teclado si el usuario está escribiendo en un Entry
        if isinstance(event.widget, tk.Entry):
            return
        tecla = event.keysym.lower()
        if tecla in self.teclas_presionadas:
            return
        self.teclas_presionadas.add(tecla)

        if tecla in ("w", "up"):
            self.enviar_comando("move 1")
        elif tecla in ("s", "down"):
            self.enviar_comando("move -1")
        elif tecla in ("a", "left"):
            self.enviar_comando("turn -1")
        elif tecla in ("d", "right"):
            self.enviar_comando("turn 1")

    def al_soltar_tecla(self, event):
        tecla = event.keysym.lower()
        self.teclas_presionadas.discard(tecla)

        if tecla in ("w", "up", "s", "down"):
            self.enviar_comando("move 0")
        elif tecla in ("a", "left", "d", "right"):
            self.enviar_comando("turn 0")

    # ==========================================================
    # VENTANA SECUNDARIA 1: LUCES
    # ==========================================================
    def abrir_ventana_luces(self):
        win = tk.Toplevel(self.root)
        win.title("Control de Luces del Vehículo")
        win.geometry("340x330")
        win.configure(bg="#1E1E2E")
        win.resizable(False, False)

        tk.Label(
            win,
            text="SISTEMA DE ILUMINACIÓN",
            fg="#F9E2AF",
            bg="#1E1E2E",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=15)

        def crear_boton_luz(padre, texto, atributo, cmd_base):
            estado_actual = getattr(self, atributo)
            btn = tk.Button(
                padre,
                text=f"{texto}: {'ON' if estado_actual else 'OFF'}",
                width=28,
                height=2,
                bg="#A6E3A1" if estado_actual else "#313244",
                fg="#1E1E2E" if estado_actual else "#CDD6F4",
                font=("Segoe UI", 10, "bold"),
            )

            def alternar():
                nuevo_estado = not getattr(self, atributo)
                setattr(self, atributo, nuevo_estado)
                btn.config(
                    text=f"{texto}: {'ON' if nuevo_estado else 'OFF'}",
                    bg="#A6E3A1" if nuevo_estado else "#313244",
                    fg="#1E1E2E" if nuevo_estado else "#CDD6F4",
                )
                self.enviar_comando(f"{cmd_base} {1 if nuevo_estado else 0}")

            btn.config(command=alternar)
            btn.pack(pady=6)

        crear_boton_luz(win, "Luces Frontales", "estado_lf", "lf")
        crear_boton_luz(win, "Luces Traseras", "estado_lb", "lb")
        crear_boton_luz(win, "Direccional Izquierda", "estado_ll", "ll")
        crear_boton_luz(win, "Direccional Derecha", "estado_lr", "lr")
        crear_boton_luz(win, "Ambas Direccionales", "estado_lboth", "lboth")

    # ==========================================================
    # VENTANA SECUNDARIA 2: DECREMENTO MANUAL (PRUEBAS 0-7)
    # ==========================================================
    def abrir_ventana_decremento_manual(self):
        win = tk.Toplevel(self.root)
        win.title("Decremento Manual (Circular de 5)")
        win.geometry("380x260")
        win.configure(bg="#1E1E2E")
        win.resizable(False, False)

        tk.Label(
            win,
            text="PRUEBA MANUAL DECREMENTADOR (0 - 7)",
            fg="#CBA6F7",
            bg="#1E1E2E",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(15, 5))

        tk.Label(
            win,
            text="Ingrese un número entero (0 a 7) para enviar\nsus 3 bits (A, B, C) al circuito físico:",
            fg="#CDD6F4",
            bg="#1E1E2E",
            font=("Segoe UI", 9),
        ).pack(pady=5)

        entrada_num = tk.Entry(
            win,
            width=12,
            justify="center",
            font=("Consolas", 16, "bold"),
            bg="#313244",
            fg="#FFFFFF",
            insertbackground="#FFFFFF",
        )
        entrada_num.pack(pady=10)
        entrada_num.focus()

        lbl_info = tk.Label(
            win,
            text="Salida esperada: (N - 5) mod 8\nLEDs: Frontales=X | Dir=Y | Traseras=Z",
            fg="#A6ADC8",
            bg="#1E1E2E",
            font=("Consolas", 9),
        )
        lbl_info.pack(pady=5)

        def enviar_manual():
            texto = entrada_num.get().strip()
            try:
                valor = int(texto)
                if 0 <= valor <= 7:
                    # Si el modo automático LDR estaba activo, se desactiva en la interfaz
                    if self.dec_ldr_activo:
                        self.dec_ldr_activo = False
                        self.btn_dec_auto.config(
                            text="Circuito Decrementador (LDR): OFF", bg="#45475A"
                        )
                    self.enviar_comando(f"dec_man {valor}")
                    esperado = (valor - 5) % 8
                    lbl_info.config(
                        text=f"Enviado: {valor} ({valor:03b}) -> Esperado: {esperado} ({esperado:03b})",
                        fg="#A6E3A1",
                    )
                else:
                    messagebox.showwarning("Valor fuera de rango", "Ingrese un número entre 0 y 7.", parent=win)
            except ValueError:
                messagebox.showerror("Entrada inválida", "Debe ingresar un número entero del 0 al 7.", parent=win)

        tk.Button(
            win,
            text="Enviar a Raspberry",
            width=22,
            height=2,
            bg="#CBA6F7",
            fg="#1E1E2E",
            font=("Segoe UI", 10, "bold"),
            command=enviar_manual,
        ).pack(pady=10)

    # ==========================================================
    # VENTANA SECUNDARIA 3: ABOUT (REQUISITO DE DOCUMENTACIÓN)
    # ==========================================================
    def abrir_ventana_about(self):
        win = tk.Toplevel(self.root)
        win.title("About - Acerca del Proyecto")
        win.geometry("430x310")
        win.configure(bg="#1E1E2E")
        win.resizable(False, False)

        tk.Label(
            win,
            text="RC Controller & Decrementador Circular 5",
            fg="#94E2D5",
            bg="#1E1E2E",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(15, 2))

        tk.Label(
            win,
            text="Versión 2.0 - Fundamentos de Sistemas Computacionales (2026)",
            fg="#A6ADC8",
            bg="#1E1E2E",
            font=("Segoe UI", 9),
        ).pack(pady=(0, 10))

        info_texto = (
            "Institución: Instituto Tecnológico de Costa Rica (TEC)\n"
            "Integrantes:\n"
            "  • Integrante 1 (Completar Nombre Completo)\n"
            "  • Integrante 2 (Completar Nombre Completo)\n\n"
            "Guía Rápida de Uso:\n"
            "1. Mantenga presionado Avanzar/Retroceder o Girar Izq/Der.\n"
            "2. Use 'Luces' para controlar faros y direccionales.\n"
            "3. Active 'Circuito Decrementador (LDR)' para lectura automática\n"
            "   de 8 rangos o 'Decremento manual' para pruebas 0-7."
        )
        tk.Label(
            win,
            text=info_texto,
            justify="left",
            fg="#CDD6F4",
            bg="#252538",
            padx=12,
            pady=12,
            font=("Segoe UI", 9),
        ).pack(padx=15, pady=5, fill="both")

    # ==========================================================
    # TOGGLE DECREMENTADOR CON FOTORRESISTENCIA
    # ==========================================================
    def toggle_decrementador_ldr(self):
        self.dec_ldr_activo = not self.dec_ldr_activo
        if self.dec_ldr_activo:
            self.btn_dec_auto.config(
                text="Circuito Decrementador (LDR): ON", bg="#A6E3A1", fg="#1E1E2E"
            )
            self.enviar_comando("dec_auto 1")
        else:
            self.btn_dec_auto.config(
                text="Circuito Decrementador (LDR): OFF", bg="#45475A", fg="#FFFFFF"
            )
            self.lbl_telemetria.config(text="Decrementador: Inactivo", fg="#A6ADC8")
            self.enviar_comando("dec_auto 0")

    # ==========================================================
    # COMUNICACIÓN POR SOCKETS (SERVIDOR EN SEGUNDO PLANO)
    # ==========================================================
    def enviar_comando(self, comando):
        if self.conectado and self.client_socket:
            try:
                self.client_socket.sendall((comando + "\n").encode())
            except Exception as e:
                print("Error enviando comando:", e)
                self.conectado = False
                self.actualizar_estado_conexion(False)

    def actualizar_estado_conexion(self, estado, ip=""):
        if estado:
            self.lbl_estado.config(
                text=f"● CONECTADO A PICO W ({ip})", fg="#A6E3A1"
            )
        else:
            self.lbl_estado.config(
                text="● DESCONECTADO - ESPERANDO RASPBERRY PI...", fg="#F38BA8"
            )

    def procesar_telemetria(self, linea):
        # Formato LDR: TELEMETRIA:LDR:<adc>:<0-7>:<bin_in>:<bin_out>:<dec_out>
        # Formato MAN: TELEMETRIA:MAN:<0-7>:<bin_in>:<bin_out>:<dec_out>
        partes = linea.strip().split(":")
        if partes[0] == "TELEMETRIA":
            if partes[1] == "LDR" and len(partes) == 7:
                _, _, adc, nivel, b_in, b_out, d_out = partes
                texto = f"LDR={adc} -> In:{nivel}({b_in}) | Out:{d_out}({b_out})"
                self.lbl_telemetria.config(text=texto, fg="#A6E3A1")
            elif partes[1] == "MAN" and len(partes) == 6:
                _, _, nivel, b_in, b_out, d_out = partes
                texto = f"Manual -> In:{nivel}({b_in}) | Out:{d_out}({b_out})"
                self.lbl_telemetria.config(text=texto, fg="#CBA6F7")

    def iniciar_servidor_socket(self):
        def hilo_servidor():
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen(1)

            while True:
                try:
                    conn, addr = server_socket.accept()
                    self.client_socket = conn
                    self.conectado = True
                    self.root.after(0, lambda a=addr[0]: self.actualizar_estado_conexion(True, a))

                    buffer_rx = ""
                    while True:
                        data = conn.recv(512)
                        if not data:
                            break
                        buffer_rx += data.decode()
                        while "\n" in buffer_rx:
                            linea, buffer_rx = buffer_rx.split("\n", 1)
                            self.root.after(0, lambda l=linea: self.procesar_telemetria(l))
                except Exception as e:
                    print("Error en socket servidor:", e)
                finally:
                    self.conectado = False
                    if self.client_socket:
                        self.client_socket.close()
                    self.root.after(0, lambda: self.actualizar_estado_conexion(False))

        threading.Thread(target=hilo_servidor, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = ControlRemotoApp(root)
    root.mainloop()