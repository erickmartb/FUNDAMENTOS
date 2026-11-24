import machine
import network
import socket
import utime
import uselect

# ==========================================================
# 1. CONFIGURACIÓN DE RED WIFI Y SERVIDOR PC
# ==========================================================
SSID = "A54 de Marianela"
PASSWORD = "Noah_1111"
SERVER_IP = "10.190.216.164"  # <-- Cambiar por la IPv4 actual de tu computadora (ipconfig)
SERVER_PORT = 8001

# ==========================================================
# 2. REGISTRO DE CORRIMIENTO 74LS164 (SISTEMA DE LUCES)
# ==========================================================
# [QA, QB, QC, QD, QE, QF, QG, QH]
# QA, QB = Frontales | QC, QD = Traseras | QE = Dir. Izq | QF = Dir. Der
AB = machine.Pin(15, machine.Pin.OUT)
CLK = machine.Pin(14, machine.Pin.OUT)

APAGADO = [0, 0, 0, 0, 0, 0, 0, 0]
estado_luces = [0, 0, 0, 0, 0, 0, 0, 0]

def ejecutar_secuencia(secuencia):
    """Envía 8 bits al registro 74LS164."""
    for i in range(8):
        bit = secuencia[7 - i]
        AB.value(bit)
        CLK.value(1)
        CLK.value(0)

ejecutar_secuencia(APAGADO)

# ==========================================================
# 3. CIRCUITO DECREMENTADOR FÍSICO (COMPUERTAS 74LSxx)
# ==========================================================
# Entradas hacia el circuito físico (MSB = A, B, LSB = C)
EntradaA = machine.Pin(0, machine.Pin.OUT)
EntradaB = machine.Pin(1, machine.Pin.OUT)
EntradaC = machine.Pin(2, machine.Pin.OUT)

# Salidas provenientes del circuito físico (MSB = X, Y, LSB = Z)
Resultado1 = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_DOWN) # Bit X (MSB)
Resultado2 = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_DOWN)  # Bit Y (Medio)
Resultado3 = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_DOWN)  # Bit Z (LSB)

EntradaA.value(0)
EntradaB.value(0)
EntradaC.value(0)

# ==========================================================
# 4. MOTORES (PUENTE H) Y FOTORRESISTENCIA (LDR)
# ==========================================================
# Motor Delantero (Dirección - Canal A)
ena = machine.PWM(machine.Pin(19))
ena.freq(1000)
ena.duty_u16(0)
in1 = machine.Pin(20, machine.Pin.OUT)
in2 = machine.Pin(21, machine.Pin.OUT)

# Motor Trasero (Tracción - Canal B)
enb = machine.PWM(machine.Pin(16))
enb.freq(1000)
enb.duty_u16(0)
in3 = machine.Pin(17, machine.Pin.OUT)
in4 = machine.Pin(18, machine.Pin.OUT)

# Sensor Fotorresistencia (ADC Pin 27 -> rango 0 a 65535)
adc_ldr = machine.ADC(machine.Pin(27))

# Variables de estado del vehículo
nivel_velocidad = 4          # Nivel PWM de 1 a 4
estado_traccion = 0          # 1: Avanzar, -1: Retroceder, 0: Detenido
estado_direccion = 0         # -1: Izquierda, 1: Derecha, 0: Recto

direccional_izq_activa = False
direccional_der_activa = False
decrementador_ldr_activo = False
decrementador_manual_activo = False

def traducir_potencia(nivel):
    nivel_limpio = abs(nivel)
    if nivel_limpio == 1: return 45000
    if nivel_limpio == 2: return 52000
    if nivel_limpio == 3: return 59000
    if nivel_limpio == 4: return 65535
    return 0

def actualizar_motores():
    """
    Aplica continuamente la tracción y dirección según los botones presionados.
    El tiempo de giro o avance depende exclusivamente de cuánto tiempo se mantenga
    presionado el botón en la interfaz.
    """
    fuerza = traducir_potencia(nivel_velocidad)
    
    # Reiniciar pines por seguridad
    in1.value(0); in2.value(0)
    in3.value(0); in4.value(0)

    # Control de Dirección (Motor Delantero)
    if estado_direccion == -1:      # Izquierda
        in1.value(1); in2.value(0)
        ena.duty_u16(fuerza)
    elif estado_direccion == 1:     # Derecha
        in1.value(0); in2.value(1)
        ena.duty_u16(fuerza)
    else:                           # Recto
        ena.duty_u16(0)

    # Control de Tracción (Motor Trasero)
    if estado_traccion == 1:        # Avanzar
        in3.value(1); in4.value(0)
        enb.duty_u16(fuerza)
    elif estado_traccion == -1:     # Retroceder
        in3.value(0); in4.value(1)
        enb.duty_u16(fuerza)
    elif estado_direccion != 0:     # Si solo se presiona girar, impulsa suavemente
        in3.value(1); in4.value(0)
        enb.duty_u16(fuerza)
    else:                           # Detenido
        enb.duty_u16(0)

# ==========================================================
# 5. LÓGICA DEL CIRCUITO DECREMENTADOR (LDR Y MANUAL)
# ==========================================================
def convertir_ldr_a_entero(lectura_adc):
    """
    Divide el rango de lectura de la fotorresistencia en 8 intervalos (0 al 7).
    adc_ldr.read_u16() devuelve valores entre 0 y 65535 (8 intervalos de 8192).
    Si tu sensor trabaja en un rango calibrado (ej. 0 a 800), ajusta el divisor a 100.
    """
    intervalo = lectura_adc // 8192
    if intervalo < 0:
        return 0
    if intervalo > 7:
        return 7
    return intervalo

def ejecutar_decrementador(valor_entrada):
    """
    1. Convierte el entero (0-7) a 3 bits (A, B, C) y los envía al circuito físico.
    2. Lee los 3 bits de salida (X, Y, Z) desde las compuertas 74LSxx.
    3. Refleja X, Y, Z en los LEDs del carro:
       - Frontales (QA, QB)     = X (MSB)
       - Direccionales (QE, QF) = Y (Bit intermedio)
       - Traseras (QC, QD)      = Z (LSB)
    """
    valor_entrada = max(0, min(7, int(valor_entrada)))

    # Extracción de los 3 bits (A = MSB, B = medio, C = LSB)
    bit_a = (valor_entrada >> 2) & 1
    bit_b = (valor_entrada >> 1) & 1
    bit_c = valor_entrada & 1

    # Enviar bits a los pines de entrada del circuito integrado
    EntradaA.value(bit_a)
    EntradaB.value(bit_b)
    EntradaC.value(bit_c)

    # Pequeña espera para estabilización eléctrica de las compuertas
    utime.sleep_ms(15)

    # Leer resultados desde el circuito físico
    bit_x = Resultado1.value()
    bit_y = Resultado2.value()
    bit_z = Resultado3.value()

    # Mostrar salida binaria en los LEDs del vehículo
    estado_luces[0] = bit_x; estado_luces[1] = bit_x  # Frontales (MSB)
    estado_luces[4] = bit_y; estado_luces[5] = bit_y  # Direccionales (Medio)
    estado_luces[2] = bit_z; estado_luces[3] = bit_z  # Traseras (LSB)
    ejecutar_secuencia(estado_luces)

    salida_decimal = (bit_x << 2) | (bit_y << 1) | bit_z
    return (bit_a, bit_b, bit_c), (bit_x, bit_y, bit_z), salida_decimal

# ==========================================================
# 6. RUTINAS DE MOVIMIENTO AUTOMÁTICO
# ==========================================================
def aplicar_circle():
    in1.value(1); in2.value(0); ena.duty_u16(traducir_potencia(4))
    in3.value(1); in4.value(0); enb.duty_u16(traducir_potencia(4))
    utime.sleep(5)
    actualizar_motores()

def aplicar_infinite():
    f = traducir_potencia(4)
    in1.value(0); in2.value(0); ena.duty_u16(f)
    in3.value(1); in4.value(0); enb.duty_u16(f)
    utime.sleep(1)

    in1.value(1); in2.value(0); ena.duty_u16(f)
    in3.value(1); in4.value(0); enb.duty_u16(f)
    utime.sleep(2.5)

    in1.value(0); in2.value(0); ena.duty_u16(f)
    in3.value(1); in4.value(0); enb.duty_u16(f)
    utime.sleep(1)

    in1.value(0); in2.value(0); ena.duty_u16(f)
    in3.value(0); in4.value(0); enb.duty_u16(f)
    utime.sleep(0.1)

    in1.value(0); in2.value(1); ena.duty_u16(f)
    in3.value(1); in4.value(0); enb.duty_u16(f)
    utime.sleep(2.5)

    in1.value(0); in2.value(0); ena.duty_u16(f)
    in3.value(1); in4.value(0); enb.duty_u16(f)
    utime.sleep(1)
    actualizar_motores()

def aplicar_zigzag():
    f = traducir_potencia(4)
    for _ in range(1):
        in1.value(1); in2.value(0); ena.duty_u16(f)
        in3.value(1); in4.value(0); enb.duty_u16(f)
        utime.sleep(1.5)
        in1.value(0); in2.value(1); ena.duty_u16(f)
        in3.value(1); in4.value(0); enb.duty_u16(f)
        utime.sleep(1.5)
    actualizar_motores()

def aplicar_especial():
    f = traducir_potencia(4)
    for i in range(25):
        if i % 2 == 0:
            estado_luces[0:6] = [1, 0, 1, 0, 1, 0]
            in1.value(0); in2.value(1); ena.duty_u16(f)
        else:
            estado_luces[0:6] = [0, 1, 0, 1, 0, 1]
            in1.value(1); in2.value(0); ena.duty_u16(f)
        in3.value(1); in4.value(0); enb.duty_u16(f)
        ejecutar_secuencia(estado_luces)
        utime.sleep(0.2)
    estado_luces[0:6] = [0, 0, 0, 0, 0, 0]
    ejecutar_secuencia(estado_luces)
    actualizar_motores()

# ==========================================================
# 7. PROCESADOR DE COMANDOS DESDE EL SOCKET WIFI
# ==========================================================
def procesar_comando(texto, sock):
    global estado_traccion, estado_direccion, nivel_velocidad
    global direccional_izq_activa, direccional_der_activa
    global decrementador_ldr_activo, decrementador_manual_activo

    partes = texto.strip().split()
    if not partes:
        return
    cmd = partes[0].lower()

    try:
        if cmd == "move":
            estado_traccion = int(partes[1]) # 1, -1, 0
            actualizar_motores()

        elif cmd == "turn":
            estado_direccion = int(partes[1]) # -1, 1, 0
            actualizar_motores()

        elif cmd == "speed":
            nivel_velocidad = max(1, min(4, int(partes[1])))
            actualizar_motores()

        elif cmd == "circle":
            aplicar_circle()

        elif cmd == "infinite":
            aplicar_infinite()

        elif cmd == "zigzag":
            aplicar_zigzag()

        elif cmd == "especial":
            aplicar_especial()

        elif cmd == "lf":
            decrementador_manual_activo = False
            v = int(partes[1])
            estado_luces[0] = v; estado_luces[1] = v
            ejecutar_secuencia(estado_luces)

        elif cmd == "lb":
            decrementador_manual_activo = False
            v = int(partes[1])
            estado_luces[2] = v; estado_luces[3] = v
            ejecutar_secuencia(estado_luces)

        elif cmd == "ll":
            decrementador_manual_activo = False
            v = int(partes[1])
            direccional_izq_activa = (v == 1)
            if not direccional_izq_activa:
                estado_luces[4] = 0
                ejecutar_secuencia(estado_luces)

        elif cmd == "lr":
            decrementador_manual_activo = False
            v = int(partes[1])
            direccional_der_activa = (v == 1)
            if not direccional_der_activa:
                estado_luces[5] = 0
                ejecutar_secuencia(estado_luces)

        elif cmd == "lboth":
            decrementador_manual_activo = False
            v = int(partes[1])
            direccional_izq_activa = (v == 1)
            direccional_der_activa = (v == 1)
            if v == 0:
                estado_luces[4] = 0; estado_luces[5] = 0
                ejecutar_secuencia(estado_luces)

        elif cmd == "dec_auto":
            v = int(partes[1])
            decrementador_ldr_activo = (v == 1)
            decrementador_manual_activo = False
            if not decrementador_ldr_activo:
                ejecutar_secuencia(APAGADO)

        elif cmd == "dec_man":
            decrementador_ldr_activo = False
            decrementador_manual_activo = True
            num = int(partes[1])
            bits_in, bits_out, res_dec = ejecutar_decrementador(num)
            msg = f"TELEMETRIA:MAN:{num}:{bits_in[0]}{bits_in[1]}{bits_in[2]}:{bits_out[0]}{bits_out[1]}{bits_out[2]}:{res_dec}\n"
            sock.sendall(msg.encode())

    except Exception as e:
        print("Error ejecutando comando:", texto, e)

# ==========================================================
# 8. CONEXIÓN WIFI Y BUCLE PRINCIPAL NO BLOQUEANTE
# ==========================================================
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while not wlan.isconnected():
        print("Conectando a WiFi...")
        utime.sleep(1)
    print("WiFi conectado. IP Pico:", wlan.ifconfig()[0])

def iniciar_cliente():
    conectar_wifi()
    while True:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            print(f"Conectando al servidor {SERVER_IP}:{SERVER_PORT}...")
            client_socket.connect((SERVER_IP, SERVER_PORT))
            client_socket.sendall(b"PICO_CONECTADA\n")
            client_socket.setblocking(False)
            print("Conectado al servidor exitosamente.")

            buffer_rx = ""
            t_parpadeo = utime.ticks_ms()
            t_ldr = utime.ticks_ms()
            estado_parpadeo = False

            while True:
                # A. Lectura no bloqueante de comandos desde la PC
                try:
                    datos = client_socket.recv(512)
                    if not datos:
                        raise ConnectionError("Servidor cerró la conexión.")
                    buffer_rx += datos.decode()
                    while "\n" in buffer_rx:
                        linea, buffer_rx = buffer_rx.split("\n", 1)
                        procesar_comando(linea, client_socket)
                except OSError:
                    pass  # Sin datos nuevos en el buffer

                ahora = utime.ticks_ms()

                # B. Parpadeo de direccionales (solo si el decrementador no usa los LEDs)
                if not decrementador_ldr_activo and not decrementador_manual_activo:
                    if utime.ticks_diff(ahora, t_parpadeo) >= 500:
                        t_parpadeo = ahora
                        estado_parpadeo = not estado_parpadeo
                        cambio = False
                        if direccional_izq_activa:
                            estado_luces[4] = 1 if estado_parpadeo else 0
                            cambio = True
                        if direccional_der_activa:
                            estado_luces[5] = 1 if estado_parpadeo else 0
                            cambio = True
                        if cambio:
                            ejecutar_secuencia(estado_luces)

                # C. Lectura continua de Fotorresistencia cuando el Decrementador está activo
                if decrementador_ldr_activo:
                    if utime.ticks_diff(ahora, t_ldr) >= 400:
                        t_ldr = ahora
                        lectura = adc_ldr.read_u16()
                        nivel_0_7 = convertir_ldr_a_entero(lectura)
                        bits_in, bits_out, res_dec = ejecutar_decrementador(nivel_0_7)
                        msg = f"TELEMETRIA:LDR:{lectura}:{nivel_0_7}:{bits_in[0]}{bits_in[1]}{bits_in[2]}:{bits_out[0]}{bits_out[1]}{bits_out[2]}:{res_dec}\n"
                        try:
                            client_socket.sendall(msg.encode())
                        except OSError:
                            pass

                utime.sleep_ms(20)

        except Exception as e:
            print("Reconectando en 3s debido a:", e)
            estado_traccion = 0
            estado_direccion = 0
            actualizar_motores()
            client_socket.close()
            utime.sleep(3)

iniciar_cliente()