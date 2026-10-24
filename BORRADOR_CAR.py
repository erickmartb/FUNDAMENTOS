import machine
import utime
import sys
import uselect

# ==========================================
# BLOQUE 1: SISTEMA DE LUCES (74LS164)
# ==========================================

# Configuración de los pines del registro de corrimiento
AB = machine.Pin(15, machine.Pin.OUT)
CLK = machine.Pin(14, machine.Pin.OUT)

# Secuencias predefinidas de LEDs
# El orden de la lista representa las salidas físicas del chip:
# [QA, QB, QC, QD, QE, QF, QG, QH]
# QA y QB = Frontales | QC y QD = Traseras Rojas | QE = Dir. Izquierda | QF = Dir. Derecha

Apagado                 = [0, 0, 0, 0, 0, 0, 0, 0] # Todo apagado
secuenciaFrontales      = [1, 1, 0, 0, 0, 0, 0, 0] # Solo luces delanteras
secuenciaRojas          = [0, 0, 1, 1, 0, 0, 0, 0] # Solo luces rojas traseras
secuenciaFR             = [1, 1, 1, 1, 0, 0, 0, 0] # Frontales y Rojas (Modo LDR oscuridad)
secuenciaDirIzquierda   = [0, 0, 0, 0, 1, 0, 0, 0] # Solo direccional izquierda
secuenciaDirDerecha     = [0, 0, 0, 0, 0, 1, 0, 0] # Solo direccional derecha
secuenciaFRDirIzquierda = [1, 1, 1, 1, 1, 0, 0, 0] # FR + Direccional Izquierda
secuenciaFRDirDerecha   = [1, 1, 1, 1, 0, 1, 0, 0] # FR + Direccional Derecha

def EjecutarSecuencia(secuencia):
    """
    Toma una lista de 8 números y la empuja al chip 74LS164.
    """
    for i in range(8):
        # 7-i hace que el ciclo lea la lista al revés 
        bit = secuencia[7-i] 
        AB.value(bit)
        CLK.value(1) 
        CLK.value(0) 

# Apagar todas las luces al iniciar la placa por seguridad
EjecutarSecuencia(Apagado)

# ==========================================
# BLOQUE 2: PINES DE MOTORES Y LECTOR DE COMANDOS
# ==========================================

# Configuración de pines de los motores
# Motor Delantero (Canal A)
ena = machine.PWM(machine.Pin(19))
ena.freq(1000)
ena.duty_u16(0) # Inicia apagado (0 fuerza)
in1 = machine.Pin(20, machine.Pin.OUT)
in2 = machine.Pin(21, machine.Pin.OUT)

# Motor Trasero (Canal B)
enb = machine.PWM(machine.Pin(16))
enb.freq(1000)
enb.duty_u16(0) # Inicia apagado (0 fuerza)
in3 = machine.Pin(17, machine.Pin.OUT)
in4 = machine.Pin(18, machine.Pin.OUT)

# Fotoresistencia
adc_ldr = machine.ADC(machine.Pin(27))

# Variables globales
potencia_actual = 0
direccional_izq_activa = False
direccional_der_activa = False
estado_luces = [0, 0, 0, 0, 0, 0, 0, 0]
modo_ldr_activo = False

# Función para asignar la potencia
def traducir_potencia(nivel):
    # abs() quita el negativo.
    nivel_limpio = abs(nivel) 
    
    if nivel_limpio == 1: return 45000  # Fuerza baja
    if nivel_limpio == 2: return 52000  # Fuerza media
    if nivel_limpio == 3: return 59000  # Fuerza alta
    if nivel_limpio == 4: return 65535  # Fuerza máxima
    return 0

# Función de adelante/atrás
def aplicar_pwm(valor):
    global potencia_actual
    potencia_actual = valor  # Guardamos el valor en la memoria del carrito
    
    fuerza = traducir_potencia(valor)
    
    # Se apagan los pines por seguridad
    in1.value(0)
    in2.value(0)
    in3.value(0)
    in4.value(0)
    
    if valor > 0:
        # AVANZAR
        # Motor Delantero (Canal A)
        in1.value(0)
        in2.value(0)
        ena.duty_u16(fuerza)
        
        # Motor Trasero (Canal B)
        in3.value(1)
        in4.value(0)
        enb.duty_u16(fuerza)
        
    elif valor < 0:
        # RETROCEDER
        # Motor Delantero
        in1.value(0)
        in2.value(0)
        ena.duty_u16(fuerza)
        
        # Motor Trasero
        in3.value(0)
        in4.value(1)
        enb.duty_u16(fuerza)
        
    else:
        # DETENER 
        ena.duty_u16(0)
        enb.duty_u16(0)
        
# Función de dirección
def aplicar_direccion(valor_dir):
    fuerza_giro = traducir_potencia(4)

    # Se apagan los pines por seguridad
    in1.value(0); in2.value(0)
    in3.value(0); in4.value(0)
    
    if valor_dir == -1:
        # GIRAR IZQUIERDA
        in1.value(0); in2.value(1); ena.duty_u16(fuerza_giro) # Delantero
        in3.value(0); in4.value(1); enb.duty_u16(fuerza_giro) # Trasero
        
    elif valor_dir == 1:
        # GIRAR DERECHA
        in1.value(1); in2.value(0); ena.duty_u16(fuerza_giro) # Delantero
        in3.value(1); in4.value(0); enb.duty_u16(fuerza_giro) # Trasero
        
    elif valor_dir == 2:
        # RETROCEDER
        in1.value(0); in2.value(0); ena.duty_u16(fuerza_giro) # Delantero
        in3.value(0); in4.value(1); enb.duty_u16(fuerza_giro) # Trasero
        
    elif valor_dir == 0:
        # SEGUIR DIRECTO
        in1.value(0); in2.value(0); ena.duty_u16(fuerza_giro) # Delantero
        in3.value(1); in4.value(0); enb.duty_u16(fuerza_giro) # Trasero
        
    # Mantenemos el carrito haciendo ese movimiento por 2 segundos completos
    utime.sleep(2.0)
    
    
    aplicar_pwm(potencia_actual)
    print("-> Giro completado. Volviendo a la normalidad.")
    
# Función circle
def aplicar_circle():
    in1.value(0)
    in2.value(0)
    in3.value(0)
    in4.value(0)

    # M Delantero
    in1.value(1)
    in2.value(0)
    ena.duty_u16(traducir_potencia(4))
    # M Trasero
    in3.value(1)
    in4.value(0)
    enb.duty_u16(traducir_potencia(4))
    utime.sleep(5)
    print("-> Circle realizado")
    aplicar_pwm(potencia_actual)
    
# Función infinite
def aplicar_infinite():
    fuerza_alta = traducir_potencia(4)
    
    in1.value(0)
    in2.value(0)
    in3.value(0)
    in4.value(0)
    
    # Medio círculo derecha
    in1.value(1); in2.value(0); ena.duty_u16(fuerza_alta)
    in3.value(1); in4.value(0); enb.duty_u16(fuerza_alta)
    utime.sleep(2.5)
    # Medio círculo izquierda
    in1.value(0); in2.value(1); ena.duty_u16(fuerza_alta)
    in3.value(1); in4.value(0); enb.duty_u16(fuerza_alta)
    utime.sleep(2.5)
    
    print("-> Infinito realizado")
    aplicar_pwm(potencia_actual)
    
# Función zigzag
def aplicar_zigzag():
    fuerza = traducir_potencia(4)
    
    in1.value(0)
    in2.value(0)
    in3.value(0)
    in4.value(0)
    
    for _ in range(3):
        # Gira 
        in1.value(1); in2.value(0); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        # Gira 
        in1.value(0); in2.value(1); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        # Gira 
        in1.value(1); in2.value(0); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        # Gira 
        in1.value(0); in2.value(1); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        # Gira 
        in1.value(1); in2.value(0); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        # Gira 
        in1.value(0); in2.value(1); ena.duty_u16(fuerza)
        in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        utime.sleep(2)
        
    print("-> Zigzag realizado")
    aplicar_pwm(potencia_actual)
    
# Función especial
def aplicar_especial():
    fuerza = traducir_potencia(4) 
    
    in1.value(0)
    in2.value(0)
    in3.value(0)
    in4.value(0)
    
    # Un ciclo de 25 por 0.2s para 5s
    for i in range(25):
        
        #"i % 2" para saber si la vuelta es par o impar. Sirve para encender unas luces y después otras
        if i % 2 == 0:
            # Lado A: [QA(1), QB(0), QC(1), QD(0), QE(1), QF(0)]
            estado_luces[0:6] = [1, 0, 1, 0, 1, 0]
        else:
            # Lado B: [QA(0), QB(1), QC(0), QD(1), QE(0), QF(1)]
            estado_luces[0:6] = [0, 1, 0, 1, 0, 1]
            
        actualizar_todas_las_luces()
        
        # Movimiento
        
        # Seguridad
        in1.value(0)
        in2.value(0)
        in3.value(0)
        in4.value(0)
        
        if i % 2 == 0:
            # Gira bruscamente a la izquierda
            in1.value(0); in2.value(1); ena.duty_u16(fuerza)
            in3.value(1); in4.value(0); enb.duty_u16(fuerza)
        else:
            # Gira bruscamente a la derecha
            in1.value(1); in2.value(0); ena.duty_u16(fuerza)
            in3.value(1); in4.value(0); enb.duty_u16(fuerza)
            
        # Pausa corta para que el parpadeo y el movimiento sean rápidos
        utime.sleep(0.2)
        
    # AL TERMINAR LOS 5 SEGUNDOS
    # Apaga luces
    estado_luces[0:6] = [0, 0, 0, 0, 0, 0]
    actualizar_todas_las_luces()
    
    print("-> Especial (Discoteca) finalizado tras 5 segundos")
    aplicar_pwm(potencia_actual) # El carrito vuelve a la normalidad
  
# LEDs
def actualizar_todas_las_luces():
    EjecutarSecuencia(estado_luces)
    
# Función que lee y clasifica los comandos
def procesar_comando(texto_ingresado):
    # .strip() quita espacios extra al inicio y final
    # .split() corta el texto donde haya un espacio. Crea una lista: ["pwm", "3"]
    partes = texto_ingresado.strip().split()
    
    # Omite instrucciones en blanco
    if len(partes) == 0:
        return
        
    # Pasa el comando a minúscula
    comando = partes[0].lower()
    
    try:
        if comando == "pwm":
            valor = int(partes[1])
            print(f"Potencia y dirección fijadas en: {valor}")
            if -4 <= valor <= 4:
                aplicar_pwm(valor)
            else:
                print("ERROR: El pwm debe estar entre -4 y 4")
            
        elif comando == "dir":
            valor = int(partes[1])
            print(f"-> Ejecutando dirección: {valor}")
            if valor in [-1, 0, 1, 2]:
                aplicar_direccion(valor)
            else:
                print("ERROR: Dir debe estar entre -1 y 2")
            
        elif comando == "circle":
            print("-> Ejecutando patrón: Círculo")
            aplicar_circle()

        elif comando == "infinite":
            print("-> Ejecutando patrón: Infinito")
            aplicar_infinite()
            
        elif comando == "zigzag":
            print("-> Ejecutando patrón: ZigZag")
            aplicar_zigzag()
            
        elif comando == "especial":
            print("-> Ejecutando patrón: Especial")
            aplicar_especial()
            
        elif comando == "lf":
            valor = int(partes[1])
            estado_luces[0] = valor  # Cambia LED QA (Frontal 1)
            estado_luces[1] = valor  # Cambia LED QB (Frontal 2)
            actualizar_todas_las_luces()
            print(f"-> Luces frontales: {valor}")
            
        elif comando == "lb":
            valor = int(partes[1])
            estado_luces[2] = valor  # Cambia LED QC (Roja 1)
            estado_luces[3] = valor  # Cambia LED QD (Roja 2)
            actualizar_todas_las_luces()
            print(f"-> Luces traseras: {valor}")
                
        elif comando == "ll":
            global direccional_izq_activa
            valor = int(partes[1])
            if valor == 1:
                direccional_izq_activa = True
                print("-> Direccional izquierda ACTIVADA (Lista para parpadear)")
            else:
                direccional_izq_activa = False 
                estado_luces[4] = 0            
                actualizar_todas_las_luces()
                print("-> Direccional izquierda APAGADA")

        elif comando == "lr":
            global direccional_der_activa
            valor = int(partes[1])
            if valor == 1:
                direccional_der_activa = True
                print("-> Direccional derecha ACTIVADA")
            else:
                direccional_der_activa = False
                estado_luces[5] = 0            
                actualizar_todas_las_luces()
                print("-> Direccional derecha APAGADA")
                
        elif comando == "ldr":
            global modo_ldr_activo
            valor = int(partes[1])
            if valor == 1:
                modo_ldr_activo = True
                print("-> Modo LDR Automático ACTIVADO")
            else:
                modo_ldr_activo = False
                # Apaga luces
                estado_luces[0] = 0; estado_luces[1] = 0
                estado_luces[2] = 0; estado_luces[3] = 0
                actualizar_todas_las_luces()
                print("-> Modo LDR Automático APAGADO")

        else:
            print("Comando no reconocido. Revisa la ortografía.")
            
    except Exception as e:
        print("Error en el formato. Ejemplo correcto: pwm 2")
        
# Configurar el lector rápido de la consola
lector_consola = uselect.poll()
lector_consola.register(sys.stdin, uselect.POLLIN)

# Variables para cronómetros
tiempo_anterior_parpadeo = utime.ticks_ms()
tiempo_anterior_ldr = utime.ticks_ms()

# Estado de la luz parpadeante 
estado_luz_parpadeo = False 

print("\n==============================")
print("SISTEMA INICIADO")
print("================================")

try:
    while True:
        
        # TAREA A: LEER LA CONSOLA (Espera 50 milisegundos)
        if lector_consola.poll(50):
            texto_ingresado = sys.stdin.readline()
            procesar_comando(texto_ingresado)


        # TAREA B: CONTROL DE DIRECCIONALES (Cronómetro de 500ms)
        ahora = utime.ticks_ms()
        
        # Compara si ya pasaron 500ms
        if utime.ticks_diff(ahora, tiempo_anterior_parpadeo) > 500:
            tiempo_anterior_parpadeo = ahora # Reinicia el cronómetro
            
            # Cambia de estado 
            estado_luz_parpadeo = not estado_luz_parpadeo 
            
            hubo_cambio = False # Para no actualizar las luces si no es necesario
            
            # Si la direccional izquierda está activada, su LED sigue el ritmo del cronómetro
            if direccional_izq_activa:
                estado_luces[4] = 1 if estado_luz_parpadeo else 0
                hubo_cambio = True
                
            # Lo mismo para la derecha
            if direccional_der_activa:
                estado_luces[5] = 1 if estado_luz_parpadeo else 0
                hubo_cambio = True
                
            # Si alguna está activa, mandamos los datos al chip 74LS164
            if hubo_cambio:
                actualizar_todas_las_luces()


        # TAREA C: CONTROL AUTOMÁTICO DE LUZ (Cronómetro de 1000ms)
        # Lee cada 1s.
        if modo_ldr_activo:
            if utime.ticks_diff(ahora, tiempo_anterior_ldr) > 1000:
                tiempo_anterior_ldr = ahora
                
                # Lee la luz
                nivel_luz = adc_ldr.read_u16() 
                
                # Si el cuarto está oscuro (menor a 25000), enciende
                if nivel_luz < 25000:
                    estado_luces[0] = 1; estado_luces[1] = 1 # Frontales (QA, QB)
                    estado_luces[2] = 1; estado_luces[3] = 1 # Rojas (QC, QD)
                else:
                    estado_luces[0] = 0; estado_luces[1] = 0 # Apagar todo
                    estado_luces[2] = 0; estado_luces[3] = 0
                    
                actualizar_todas_las_luces()

except KeyboardInterrupt:
    EjecutarSecuencia(Apagado)
    ena.duty_u16(0); enb.duty_u16(0)
    print("\n==============================")
    print("SISTEMA FINALIZADO")
    print("================================")