import os
import sqlite3
import asyncio
import threading
import re
import random
import unicodedata
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from flask import Flask

# === CONFIGURACION ===
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8840107743:AAFNg1W9aSNMH_4vxYyPUfFFHgsCfYMsJZA")

# === SERVICIO WEB PARA KEEP-ALIVE ===
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "OK", 200

def run_web():
    import os
    port = int(os.environ.get('PORT', 10000))
    for p in [port, 10001, 10002, 10003]:
        try:
            flask_app.run(host='0.0.0.0', port=p, use_reloader=False)
            break
        except OSError:
            print(f"Puerto {p} ocupado, intentando con el siguiente...")
            continue

# ============= BASE DE DATOS =============
def iniciar_bd():
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    
    # Crear tabla con la nueva estructura (incluyendo emblema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_telegram INTEGER PRIMARY KEY,
            nombre TEXT,
            casa TEXT,
            emblema TEXT,
            cargo TEXT,
            puntos_totales INTEGER DEFAULT 0,
            fecha_registro TIMESTAMP
        )
    ''')
    
    # Si la tabla ya existía sin la columna emblema, la agregamos
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN emblema TEXT DEFAULT '❤️'")
    except sqlite3.OperationalError:
        pass  # La columna ya existe, no pasa nada
    
    conn.commit()
    conn.close()

# ============= FUNCIONES AUXILIARES =============
def defensa_numero(numero):
    tabla = {
        '1': '⬅️', '2': '⬅️', '3': '⬆️',
        '4': '➡️', '5': '⬅️', '6': '➡️',
        '7': '➡️', '8': '⬆️', '9': '⬆️'
    }
    return tabla.get(numero, '❌')

#======== DISPARO ALEATORIO =======
def generar_disparo_aleatorio():
    aros = ["🅰️", "🅱️", "🅾️"]
    aro = random.choice(aros)
    numeros = ''.join([str(random.randint(1, 9)) for _ in range(3)])
    return "🤍", aro, numeros  # Corazón blanco para el bot

#=== GENERAR SECUENCIA DE SNITCH ===

def generar_secuencia():
    direcciones = ['ARRIBA', 'ABAJO', 'DERECHA', 'IZQUIERDA']
    longitud = random.randint(6, 10)
    palabras = random.choices(direcciones, k=longitud)
    flechas = ''.join([
        p.replace('ARRIBA', '⬆️').replace('ABAJO', '⬇️').replace('DERECHA', '➡️').replace('IZQUIERDA', '⬅️') 
        for p in palabras
    ])
    return palabras, flechas

#======== GOLPE ALEATORIO =========
def generar_golpe_aleatorio():
    numeros = ''.join([str(random.randint(1, 9)) for _ in range(3)])
    return numeros

# ============= COMANDOS =============
async def start(update, context):
    user_id = update.effective_user.id
    nombre = update.effective_user.first_name
    
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id_telegram = ?", (user_id,))
    usuario = cursor.fetchone()
    conn.close()

    # Botones de acceso rápido
    keyboard = [
        [InlineKeyboardButton("📝 Crear cuenta", callback_data="crear_cuenta")],
        [InlineKeyboardButton("🔧 Modificar cuenta", callback_data="modificar_cuenta")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if usuario is None:
        # Usuario nuevo: mostrar botones de selección de casa
        keyboard = [
            [InlineKeyboardButton("❤️ Galkin", callback_data="casa_Galkin")],
            [InlineKeyboardButton("💜 Darfor", callback_data="casa_Darfor")],
            [InlineKeyboardButton("💚 Olsson", callback_data="casa_Olsson")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✨ ¡Bienvenido {nombre} al Durmstrang's Quidditch! ✨\n\n"
            "Para comenzar, elige tu casa tocando un botón:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # Usuario existente: mostrar botones de acciones
        keyboard_acciones = [
            [InlineKeyboardButton("📚 Aprender", callback_data="ir_a_aprender")],
            [InlineKeyboardButton("🏋️ Practicar", callback_data="ir_a_practicar")],
            [InlineKeyboardButton("🏆 Jugar", callback_data="ir_a_jugar")],
            [InlineKeyboardButton("🔧 Modificar cuenta", callback_data="modificar_cuenta")]
        ]
        reply_markup_acciones = InlineKeyboardMarkup(keyboard_acciones)

        await update.message.reply_text(
            f"¡Bienvenido de vuelta {usuario[1]}!\n"
            f"Casa: {usuario[2]}\n"
            f"Cargo: {usuario[3]}\n\n"
            "¿Qué deseas hacer?",
            reply_markup=reply_markup_acciones,
            parse_mode="Markdown"
        )

async def crear_cuenta(update, context):
    await update.message.reply_text(
        "Vamos a crear tu cuenta.\n\n"
        "Primero, elige tu casa:\n"
        "❤️ Galkin\n"
        "💜 Darfor\n"
        "💚 Olsson\n\n"
        "Escribe el nombre de tu casa."
    )
    context.user_data['esperando_casa'] = True

async def manejar_mensajes(update, context):
    practica = context.user_data.get('practica_activa')
    
    if practica == 'cazador':
        mensaje = update.message.text
        
        if mensaje.lower() == 'salir':
            context.user_data['practica_activa'] = None
            context.user_data['pases_cazador'] = 0
            await update.message.reply_text("✅ Práctica de Cazador finalizada. Usa /practicar para volver.")
            return
        
        # Inicializar contador de pases si no existe
        if 'pases_cazador' not in context.user_data:
            context.user_data['pases_cazador'] = 0
            context.user_data['pases_realizados'] = []
        
        # Verificar si es un pase (formato: [Casa]🏉@usuario)
        if '🏉' in mensaje and '@' in mensaje:
            context.user_data['pases_cazador'] += 1
            context.user_data['pases_realizados'].append(mensaje)
            pases_actuales = context.user_data['pases_cazador']
            
            if pases_actuales < 4:
                await update.message.reply_text(
                    f"✅ Pase correcto. Llevas {pases_actuales}/4 pases minimos para disparo.\n"
                    f"Sigue pasando la Quaffle. (máximo 10 pases)"
                )
            elif 4 <= pases_actuales <= 10:
                await update.message.reply_text(
                    f"✅ Pase correcto. Llevas {pases_actuales} pases.\n\n"
                    f"🎯 ¡Ya puedes disparar! Usa el formato:\n"
                    f"`🤍🏉🅰️123`\n\n"
                    f"(Recuerda: 3 números del 1 al 9)"
                )
            else:
                await update.message.reply_text(
                    f"❌ Demasiados pases ({pases_actuales}). Máximo 10.\n"
                    f"Pierdes la Quaffle. Práctica reiniciada."
                )
                context.user_data['pases_cazador'] = 0
                context.user_data['pases_realizados'] = []
        
        # Verificar si es un disparo (formato: [Casa]🏉[Aro][3 números])
        elif '🏉' in mensaje and (
            '🅰' in mensaje or '🇦' in mensaje or '🅰️' in mensaje or 'A' in mensaje or
            '🅱' in mensaje or '🇧' in mensaje or '🅱️' in mensaje or 'B' in mensaje or
            '🅾' in mensaje or '🇴' in mensaje or '🅾️' in mensaje or 'O' in mensaje):

            pases = context.user_data.get('pases_cazador', 0)
        
            if pases < 4:
                await update.message.reply_text(
                    f"❌ No puedes disparar todavía. Llevas solo {pases}/4 pases.\n"
                    f"Completa los pases mínimos primero."
                )
            else:
                # Extraer números
                numeros = re.findall(r'[1-9]', mensaje)
            
                if len(numeros) == 3:
                    flechas = ''.join([defensa_numero(n) for n in numeros])
                
                    # Detectar qué aro usó
                    aro = None
                    if '🅰' in mensaje or '🇦' in mensaje or '🅰️' in mensaje or 'A' in mensaje:
                        aro = '🅰️'
                    elif '🅱' in mensaje or '🇧' in mensaje or '🅱️' in mensaje or 'B' in mensaje:
                        aro = '🅱️'
                    elif '🅾' in mensaje or '🇴' in mensaje or '🅾️' in mensaje or 'O' in mensaje:
                        aro = '🅾️'
                    else:
                        aro = '?'                
                    # Detectar qué casa usó
                    casa = "❤️" if '❤️' in mensaje else "💜" if '💜' in mensaje else "💚" if '💚' in mensaje else "?"
                
                    await update.message.reply_text(
                        f"🎯 ¡Disparo realizado!\n"
                        f"Casa: {casa} | Aro: {aro}\n"
                        f"Números: {''.join(numeros)}\n\n"
                        f"🟡 Defensa del guardián: {flechas}\n\n"
                        f"✅ ¡GOL! +100 puntos"
                    )
                
                    # Reiniciar práctica después del gol
                    context.user_data['pases_cazador'] = 0
                    context.user_data['pases_realizados'] = []
                else:
                    await update.message.reply_text(
                        f"❌ Disparo inválido. Debes usar EXACTAMENTE 3 números (1-9).\n"
                        f"Ejemplo: `🤍🏉🅰️123`\n"
                        f"Tú usaste {len(numeros)} números: {''.join(numeros) if numeros else 'ninguno'}"
                    )
        
        else:
            await update.message.reply_text(
                f"❌ Formato no reconocido.\n\n"
                f"📝 **Formato de pase:**\n"
                f"`🤍🏉@cazador2`\n\n"
                f"🎯 **Formato de disparo:**\n"
                f"`🤍🏉🅰️123`\n\n"
                f"Escribe 'salir' para terminar."
            )
    
    elif practica == 'guardian':
        mensaje = update.message.text
        casa_usuario = context.user_data.get('casa_usuario', '❤️')
        emblema_usuario = context.user_data.get('emblema_usuario', '❤️')
        
        if mensaje.lower() == 'salir':
            aciertos = context.user_data.get('guardian_aciertos', 0)
            fallos = context.user_data.get('guardian_fallos', 0)
            context.user_data['practica_activa'] = None
            await update.message.reply_text(
                f"✅ *Práctica de Guardián finalizada.*\n\n"
                f"📊 *Estadísticas:*\n"
                f"• Aciertos: {aciertos}\n"
                f"• Fallos: {fallos}\n\n"
                f"¿Qué deseas hacer?\n"
                f"/aprender - Ver reglas del juego\n"
                f"/practicar- Entrenar otra posición\n"
                f"/jugar - Iniciar una partida",
                parse_mode="Markdown"
            )
            return
        
        # Esperando confirmación "si"
        if context.user_data.get('guardian_esperando_listo'):
            if mensaje.lower() == 'si':
                context.user_data['guardian_esperando_listo'] = False
                context.user_data['guardian_esperando_defensa'] = True
                
                # Generar primer disparo
                casa, aro, numeros = generar_disparo_aleatorio()  # casa = "🤍"
                context.user_data['disparo_actual'] = {'casa': casa, 'aro': aro, 'numeros': numeros}
                context.user_data['defensa_correcta'] = ''.join([defensa_numero(n) for n in numeros])
                
                # Mostrar tabla de conversión completa
                tabla = "(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️"
                      
                await update.message.reply_text(
                    f"⚡ *¡PRIMER DISPARO!* ⚡\n\n"
                    f"`{casa}🏉{aro}{numeros}`\n\n"
                    f"📊 *TABLA DE CONVERSIÓN:*\n"
                    f"`{tabla}`\n\n"
                    f"📝 *Formato de defensa:*\n"
                    f"`{emblema_usuario}🧹{aro}⬅️⬆️➡️`\n\n"
                    f"🛡️ *Escribe tu defensa (usa solo flechas):*",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"🟡 *Esperando confirmación.*\n\n"
                    f"Escribe *'si'* cuando estés listo.\n"
                    f"Escribe *'salir'* para terminar.",
                    parse_mode="Markdown"
                )
            return
        
        # Defendiendo disparo actual
        if context.user_data.get('guardian_esperando_defensa'):
            disparo = context.user_data.get('disparo_actual', {})
            defensa_correcta = context.user_data.get('defensa_correcta', '')
            
            # ========== DIAGNÓSTICO PROFUNDO ==========
            # Mostrar el mensaje original
            #await update.message.reply_text(
            #    f"🔍 *DIAGNÓSTICO - LO QUE RECIBÍ:*\n"
            #    f"`{mensaje}`\n\n"
            #    f"*Contenido del mensaje (caracter a caracter):*\n"
            #    f"`{list(mensaje)}`\n\n"
            #    f"*Códigos Unicode de cada caracter:*\n"
            #    f"`{[hex(ord(c)) for c in mensaje]}`\n\n"
           #     f"*Lo que esperaba:*\n"
           #     f"Defensa correcta: `{emblema_usuario}🧹{disparo.get('aro')}{defensa_correcta}`\n\n"
           #     f"*Tu casa debería ser:* {emblema_usuario}\n"
           #     f"*Aro del disparo:* {disparo.get('aro')}\n\n"
           #     f"*Flechas correctas:* {defensa_correcta}\n\n"
            #    f"📝 *Escribe exactamente (copia y pega esto):*\n"
             #   f"`{emblema_usuario}🧹{disparo.get('aro')}{defensa_correcta}`",
           #     parse_mode="Markdown"
          #  )
            
            # Extraer flechas del mensaje (para diagnóstico)
           # flechas_map = {
            #    '⬆️': '⬆️', '⬆': '⬆️', '↑': '⬆️',
            #    '⬇️': '⬇️', '⬇': '⬇️', '↓': '⬇️',
              #  '➡️': '➡️', '➡': '➡️', '→': '➡️',
             #   '⬅️': '⬅️', '⬅': '⬅️', '←': '⬅️'
           # }
          #  flechas_encontradas = []
          #  for char in mensaje:
                # Normalizar el carácter para eliminar variantes invisibles
             #   normalizado = unicodedata.normalize('NFKC', char)
             #   if normalizado in flechas_map:
                    #flechas_encontradas.append(flechas_map[normalizado])
             #   elif char in flechas_map:
       #flechas_encontradas.append(flechas_map[char])
          #  flechas_str = ''.join(flechas_encontradas)
            
            # Línea de depuración (la puedes borrar después)
           # print(f"DEBUG: flechas_str = '{flechas_str}', longitud = {len(flechas_str)}")
            
            # Mostrar las flechas que se extrajeron
           # await update.message.reply_text(
             #   f"🔍 *EXTRACCIÓN DE FLECHAS:*\n"
             #   f"Flechas encontradas: `{flechas_str}`\n"
              #  f"Longitud: {len(flechas_str)} de 3 esperadas\n\n"
              #  f"Comparación:\n"
              #  f"Tus flechas: `{flechas_str}`\n"
              #  f"Flechas correctas: `{defensa_correcta}`\n"
             #   f"¿Coinciden? {'✅ SÍ' if flechas_str == defensa_correcta else '❌ NO'}",
              #  parse_mode="Markdown"
           # )
            #return  # Salimos para no procesar más
            
            # ========== EXTRAER FLECHAS (MÚLTIPLES VARIANTES) ==========
# Normalizar flechas (eliminar caracteres extra como U+FE0F)
            flechas_map = {
                '⬆️': '⬆️', '⬆': '⬆️', '↑': '⬆️',
                '⬇️': '⬇️', '⬇': '⬇️', '↓': '⬇️',
                '➡️': '➡️', '➡': '➡️', '→': '➡️',
                '⬅️': '⬅️', '⬅': '⬅️', '←': '⬅️'
            }
            flechas_encontradas = []
            for char in mensaje:
                # Normalizar el carácter para eliminar variantes invisibles
                normalizado = unicodedata.normalize('NFKC', char)
                if normalizado in flechas_map:
                    flechas_encontradas.append(flechas_map[normalizado])
                elif char in flechas_map:
                    flechas_encontradas.append(flechas_map[char])
            flechas_str = ''.join(flechas_encontradas)
            
            # Línea de depuración (la puedes borrar después)
            print(f"DEBUG: flechas_str = '{flechas_str}', longitud = {len(flechas_str)}")
            
            # Extraer aro del mensaje (aceptando múltiples variantes)
            aro_usado = None
            if '🅰' in mensaje or '🇦' in mensaje or '🅰️' in mensaje or 'A' in mensaje:
                aro_usado = '🅰️'
            elif '🅱' in mensaje or '🇧' in mensaje or '🅱️' in mensaje or 'B' in mensaje:
                aro_usado = '🅱️'
            elif '🅾' in mensaje or '🇴' in mensaje or '🅾️' in mensaje or 'O' in mensaje:
                aro_usado = '🅾️'
            
            # Verificar que se usó la casa correcta del usuario (el emblema corazón)
            casa_usada = None
            if emblema_usuario == '❤️' and '❤️' in mensaje:
                casa_usada = '❤️'
            elif emblema_usuario == '💜' and '💜' in mensaje:
                casa_usada = '💜'
            elif emblema_usuario == '💚' and '💚' in mensaje:
                casa_usada = '💚'
            
            tiene_escoba = '🧹' in mensaje
            
            # Validar defensa
            if len(flechas_str) == 6 and aro_usado == disparo.get('aro') and casa_usada == emblema_usuario and tiene_escoba:
                if flechas_str == defensa_correcta:
                    aciertos = context.user_data.get('guardian_aciertos', 0) + 1
                    context.user_data['guardian_aciertos'] = aciertos
                    
                    await update.message.reply_text(
                        f"✅ *¡DEFENSA EXITOSA!*\n\n"
                        f"Disparo: {disparo.get('casa')}🏉{disparo.get('aro')}{disparo.get('numeros')}\n"
                        f"Tu defensa: {casa_usada}🧹{aro_usado}{flechas_str}\n\n"
                        f"📊 *Aciertos:* {aciertos} | *Fallos:* {context.user_data.get('guardian_fallos', 0)}",
                        parse_mode="Markdown"
                    )
                else:
                    fallos = context.user_data.get('guardian_fallos', 0) + 1
                    context.user_data['guardian_fallos'] = fallos
                    
                    await update.message.reply_text(
                        f"❌ *¡DEFENSA FALLIDA!*\n\n"
                        f"Disparo: {disparo.get('casa')}🏉{disparo.get('aro')}{disparo.get('numeros')}\n"
                        f"Tu defensa: {casa_usada}🧹{aro_usado}{flechas_str}\n"
                        f"*Defensa correcta:* `{disparo.get('casa')}🧹{disparo.get('aro')}{defensa_correcta}`\n\n"
                        f"📊 *Aciertos:* {context.user_data.get('guardian_aciertos', 0)} | *Fallos:* {fallos}",
                        parse_mode="Markdown"
                    )
                
                # Generar nuevo disparo
                casa, aro, numeros = generar_disparo_aleatorio()
                context.user_data['disparo_actual'] = {'casa': casa, 'aro': aro, 'numeros': numeros}
                context.user_data['defensa_correcta'] = ''.join([defensa_numero(n) for n in numeros])
                
                tabla = "(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️"
                
                await update.message.reply_text(
                    f"🔄 *NUEVO DISPARO:*\n\n"
                    f"`{casa}🏉{aro}{numeros}`\n\n"
                    f"📊 *TABLA DE CONVERSIÓN:*\n"
                    f"`{tabla}`\n\n"
                    f"🛡️ *Escribe tu defensa (usa tu emblema {emblema_usuario} y escoba 🧹):*",
                    parse_mode="Markdown"
                )
            else:
                # Mensaje de error con recordatorios
                errores = []
                if casa_usada != emblema_usuario:
                    errores.append(f"• Usa el emblema de tu casa {emblema_usuario}")
                if not tiene_escoba:
                    errores.append("• Falta la escoba `🧹`")
                if aro_usado != disparo.get('aro'):
                    errores.append(f"• Usa el mismo aro del disparo ({disparo.get('aro')})")
                if len(flechas_str) != 3:
                    errores.append("• Usa exactamente 3 flechas (`⬅️`, `⬆️`, `➡️`)")
                
                recordatorio = "\n".join(errores)
                
                # Mostrar tabla de conversión para ayudar
                tabla = "(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️"
                
                await update.message.reply_text(
                    f"❌ *Formato incorrecto.*\n\n"
                    f"📝 *Recordatorio:*\n"
                    f"{recordatorio}\n\n"
                    f"📊 *TABLA DE CONVERSIÓN:*\n"
                    f"`{tabla}`\n\n"
                    f"📝 *Formato correcto:*\n"
                    f"`{emblema_usuario}🧹{disparo.get('aro')}⬆️⬇️➡️`\n\n"
                    f"🛡️ *Intenta de nuevo con el mismo disparo:*",
                    parse_mode="Markdown"
                )
            return

    elif practica == 'golpeador':
        mensaje = update.message.text
        emblema_usuario = context.user_data.get('emblema_usuario', '❤️')
    
        if mensaje.lower() == 'salir':
            aciertos = context.user_data.get('golpeador_aciertos', 0)
            fallos = context.user_data.get('golpeador_fallos', 0)
            context.user_data['practica_activa'] = None
            await update.message.reply_text(
                f"✅ *Práctica de Golpeador finalizada.*\n\n"
                f"📊 *Estadísticas:*\n"
                f"• Aciertos: {aciertos}\n"
                f"• Fallos: {fallos}\n\n"
                f"¿Qué deseas hacer?\n"
                f"/aprender - Ver reglas del juego\n"
                f"/practicar - Entrenar otra posición\n"
                f"/jugar - Iniciar una partida",
                parse_mode="Markdown"
            )
            return
    
        # Elegir modo
        if mensaje.lower() == 'atacar':
            context.user_data['golpeador_modo'] = 'atacar'
            context.user_data['golpeador_esperando'] = True
            await update.message.reply_text(
                f"⚔️ *PREPARA TU ATAQUE!* ⚔️\n\n"
                f"📝 *Escribe tu golpe con este formato:*\n"
                f"`{emblema_usuario}🏏💥123@DurmstrangQuidditchBot`\n\n"
                f"(Reemplaza '123' por 3 números de tu elección)\n\n"
                f"⚡ *Escribe tu ataque:*",
                parse_mode="Markdown"
            )
            return
    
        elif mensaje.lower() == 'defender':
            # Bot ataca con números aleatorios
            numeros_bot = ''.join([str(random.randint(1, 9)) for _ in range(3)])
            context.user_data['golpeador_modo'] = 'defender'
            context.user_data['numeros_bot'] = numeros_bot
            context.user_data['golpeador_esperando'] = True
        
            await update.message.reply_text(
                f"💥 *¡EL BOT TE ATACA!* 💥\n\n"
                f"🔢 *Números del golpe:* {numeros_bot}\n\n"
                f"🛡️ *Escribe tu defensa con este formato:*\n"
                f"`{emblema_usuario}🧹[3 flechas]🏏❌`\n\n"
                f"📊 *TABLA DE CONVERSIÓN:*\n"
                f"(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️\n\n"
                f"⚡ *Escribe tu defensa:*",
                parse_mode="Markdown"
            )
            return
    
        # Procesar ataque o defensa
        if context.user_data.get('golpeador_esperando'):
            modo = context.user_data.get('golpeador_modo')
        
            if modo == 'atacar':
                # Verificar formato de ataque
                if emblema_usuario in mensaje and '🏏💥' in mensaje and '@' in mensaje:
                    numeros = re.findall(r'[1-9]', mensaje)
                    if len(numeros) == 3:
                        # Ataque válido
                        aciertos = context.user_data.get('golpeador_aciertos', 0) + 1
                        context.user_data['golpeador_aciertos'] = aciertos
                        await update.message.reply_text(
                            f"✅ *¡GOLPE EXITOSO!*\n\n"
                            f"Tu ataque: {mensaje}\n"
                            f"📊 *Aciertos:* {aciertos} | *Fallos:* {context.user_data.get('golpeador_fallos', 0)}",
                            parse_mode="Markdown"
                        )
                    else:
                        fallos = context.user_data.get('golpeador_fallos', 0) + 1
                        context.user_data['golpeador_fallos'] = fallos
                        await update.message.reply_text(
                            f"❌ *¡GOLPE FALLIDO!*\n\n"
                            f"Debes usar EXACTAMENTE 3 números (1-9).\n"
                            f"📊 *Aciertos:* {context.user_data.get('golpeador_aciertos', 0)} | *Fallos:* {fallos}",
                            parse_mode="Markdown"
                        )
                else:
                    fallos = context.user_data.get('golpeador_fallos', 0) + 1
                    context.user_data['golpeador_fallos'] = fallos
                    await update.message.reply_text(
                        f"❌ *Formato de ataque incorrecto.*\n\n"
                        f"📝 *Formato correcto:*\n"
                        f"`{emblema_usuario}🏏💥123@DurmstrangQuidditchBot`\n\n"
                        f"📊 *Aciertos:* {context.user_data.get('golpeador_aciertos', 0)} | *Fallos:* {fallos}",
                        parse_mode="Markdown"
                    )
            
                context.user_data['golpeador_esperando'] = False
                await update.message.reply_text(
                    f"⚡ *¿Qué deseas hacer ahora?*\n"
                    f"Escribe *'atacar'* para otro golpe.\n"
                    f"Escribe *'defender'* para que el bot te ataque.\n"
                    f"Escribe *'salir'* para terminar.",
                    parse_mode="Markdown"
                )
        
            elif modo == 'defender':
                                # ========== DIAGNÓSTICO EXHAUSTIVO ==========
                #numeros_bot = context.user_data.get('numeros_bot', '')
                #defensa_correcta = ''.join([defensa_numero(n) for n in numeros_bot])
                
                # Verificar componentes básicos
                #tiene_emblema = emblema_usuario in mensaje
                #tiene_escoba = '🧹' in mensaje
                #tiene_marca_defensa = '🏏❌' in mensaje
                
                # Extracción SIN normalizar (para diagnóstico)
                #flechas_sin_normalizar = re.findall(r'[⬆️⬇️➡️⬅️]', mensaje)
                #flechas_sin_normalizar_str = ''.join(flechas_sin_normalizar)
                
                # ========== NORMALIZAR FLECHAS ==========
                #flechas_map = {
                #    '⬆️': '⬆️', '⬆': '⬆️', '↑': '⬆️',
                #    '⬇️': '⬇️', '⬇': '⬇️', '↓': '⬇️',
                #    '➡️': '➡️', '➡': '➡️', '→': '➡️',
                #    '⬅️': '⬅️', '⬅': '⬅️', '←': '⬅️'
                #}
                #flechas_normalizadas = []
                #for char in mensaje:
                #    normalizado = unicodedata.normalize('NFKC', char)
                #    if normalizado in flechas_map:
                #        flechas_normalizadas.append(flechas_map[normalizado])
                #    elif char in flechas_map:
                #        flechas_normalizadas.append(flechas_map[char])
                #flechas_normalizadas_str = ''.join(flechas_normalizadas)
                #flechas_count = len(flechas_normalizadas_str)
                
                ## Comparación
                #flechas_correctas = (flechas_normalizadas_str == defensa_correcta)
                #longitud_correcta = (flechas_count == 3)
                
                # Diagnóstico detallado
                #diagnostico = (
                #    f"🔍 *DIAGNÓSTICO GOLPEADOR - DEFENSA* 🔍\n\n"
                #    f"📨 *Mensaje recibido:*\n`{mensaje}`\n\n"
                #    f"📊 *Validación de componentes:*\n"
                #    f"• Emblema correcto ({emblema_usuario}): {'✅ SÍ' if tiene_emblema else '❌ NO'}\n"
                #    f"• Escoba (🧹): {'✅ SÍ' if tiene_escoba else '❌ NO'}\n"
                #    f"• Marca defensa (🏏❌): {'✅ SÍ' if tiene_marca_defensa else '❌ NO'}\n\n"
                #    f"🔢 *Números del bot:* {numeros_bot}\n"
                #    f"🛡️ *Defensa correcta esperada:* `{defensa_correcta}`\n\n"
                #    f"🔬 *Flechas SIN normalizar:* `{flechas_sin_normalizar_str}`\n"
                #    f"*Cantidad sin normalizar:* {len(flechas_sin_normalizar_str)}\n\n"
                #    f"🔬 *Flechas NORMALIZADAS:* `{flechas_normalizadas_str}`\n"
                #    f"*Cantidad normalizada:* {flechas_count}\n\n"
                #    f"*Comparación:*\n"
                #    f"• ¿Longitud correcta? (3): {'✅ SÍ' if longitud_correcta else f'❌ NO (tienes {flechas_count})'}\n"
                #    f"• ¿Flechas correctas?: {'✅ SÍ' if flechas_correctas else '❌ NO'}\n\n"
                #    f"📝 *Para acertar, escribe exactamente:*\n"
                #    f"`{emblema_usuario}🧹{defensa_correcta}🏏❌`"
                #)
                
                #await update.message.reply_text(diagnostico, parse_mode="Markdown")
                #return  # Salimos para no procesar más
                 
                numeros_bot = context.user_data.get('numeros_bot', '')
                defensa_correcta = ''.join([defensa_numero(n) for n in numeros_bot])
                
                # ========== NORMALIZAR FLECHAS ==========
                flechas_map = {
                    '⬆️': '⬆️', '⬆': '⬆️', '↑': '⬆️',
                    '⬇️': '⬇️', '⬇': '⬇️', '↓': '⬇️',
                    '➡️': '➡️', '➡': '➡️', '→': '➡️',
                    '⬅️': '⬅️', '⬅': '⬅️', '←': '⬅️'
                }
                flechas_normalizadas = []
                for char in mensaje:
                    normalizado = unicodedata.normalize('NFKC', char)
                    if normalizado in flechas_map:
                        flechas_normalizadas.append(flechas_map[normalizado])
                    elif char in flechas_map:
                        flechas_normalizadas.append(flechas_map[char])
                flechas_str = ''.join(flechas_normalizadas)
                flechas_count = len(flechas_str)
                
                # Verificar formato
                if emblema_usuario in mensaje and '🧹' in mensaje and '🏏❌' in mensaje:
                    if flechas_count == 6 and flechas_str == defensa_correcta:
                        aciertos = context.user_data.get('golpeador_aciertos', 0) + 1
                        context.user_data['golpeador_aciertos'] = aciertos
                        await update.message.reply_text(
                            f"✅ *¡DEFENSA EXITOSA!*\n\n"
                            f"El bot atacó con: {numeros_bot}\n"
                            f"Tu defensa: {flechas_str}\n\n"
                            f"📊 *Aciertos:* {aciertos} | *Fallos:* {context.user_data.get('golpeador_fallos', 0)}",
                            parse_mode="Markdown"
                        )
                    else:
                        fallos = context.user_data.get('golpeador_fallos', 0) + 1
                        context.user_data['golpeador_fallos'] = fallos
                        await update.message.reply_text(
                            f"❌ *¡DEFENSA FALLIDA!*\n\n"
                            f"El bot atacó con: {numeros_bot}\n"
                            f"Tu defensa: {flechas_str}\n"
                            f"Defensa correcta: {defensa_correcta}\n\n"
                            f"📊 *Aciertos:* {context.user_data.get('golpeador_aciertos', 0)} | *Fallos:* {fallos}",
                            parse_mode="Markdown"
                        )
                else:
                    fallos = context.user_data.get('golpeador_fallos', 0) + 1
                    context.user_data['golpeador_fallos'] = fallos
                    await update.message.reply_text(
                        f"❌ *Formato de defensa incorrecto.*\n\n"
                        f"📝 *Formato correcto:*\n"
                        f"`{emblema_usuario}🧹{defensa_correcta}🏏❌`\n\n"
                        f"📊 *Aciertos:* {context.user_data.get('golpeador_aciertos', 0)} | *Fallos:* {fallos}",
                        parse_mode="Markdown"
                    )
                
                context.user_data['golpeador_esperando'] = False
                await update.message.reply_text(
                    f"⚡ *¿Qué deseas hacer ahora?*\n"
                    f"Escribe *'atacar'* para golpear al bot.\n"
                    f"Escribe *'defender'* para que el bot te ataque.\n"
                    f"Escribe *'salir'* para terminar.",
                    parse_mode="Markdown"
                )
    
        else:
            await update.message.reply_text(
                f"🟢 *PRÁCTICA DE GOLPEADOR*\n\n"
                f"Escribe *'atacar'* para golpear al bot.\n"
                f"Escribe *'defender'* para que el bot te ataque.\n"
                f"Escribe *'salir'* para terminar.",
                parse_mode="Markdown"
            )

    elif practica == 'buscador':
        mensaje = update.message.text
        emblema_usuario = context.user_data.get('emblema_usuario', '❤️')
        
        if mensaje.lower() == 'salir':
            aciertos = context.user_data.get('buscador_aciertos', 0)
            fallos = context.user_data.get('buscador_fallos', 0)
            context.user_data['practica_activa'] = None
            await update.message.reply_text(
                f"✅ *Práctica de Buscador finalizada.*\n\n"
                f"📊 *Estadísticas:*\n"
                f"• Snitches capturadas: {aciertos}\n"
                f"• Snitches perdidas: {fallos}\n\n"
                f"¿Qué deseas hacer?\n"
                f"/aprender - Ver reglas del juego\n"
                f"/practicar - Entrenar otra posición\n"
                f"/jugar - Iniciar una partida",
                parse_mode="Markdown"
            )
            return
        
        # Iniciar práctica
        if mensaje.lower() == 'empezar':
            snitches_restantes = context.user_data.get('buscador_snitches_restantes', 3)
            if snitches_restantes <= 0:
                await update.message.reply_text(
                    f"🎉 *¡PRÁCTICA COMPLETADA!* 🎉\n\n"
                    f"Capturaste {context.user_data.get('buscador_aciertos', 0)} de 3 snitches.\n\n"
                    f"Usa /practicar para volver a entrenar.",
                    parse_mode="Markdown"
                )
                context.user_data['practica_activa'] = None
                return
            
            # Generar secuencia
            palabras, flechas = generar_secuencia()
            context.user_data['secuencia_actual'] = flechas
            context.user_data['buscador_esperando_respuesta'] = True
            
            direcciones_str = '/'.join(palabras)
            
            await update.message.reply_text(
                f"✨ *¡SNITCH DETECTADA!* ✨\n\n"
                f"🔅 *Secuencia de la snitch:*\n"
                f"`{direcciones_str}`\n\n"
                f"📝 *Responde con el formato:*\n"
                f"`{emblema_usuario}🧹🖐🏻⬅️⬇️⬆️➡️🔅✊🏻`\n\n"
                f"⚡ *¡Responde rápido!*",
                parse_mode="Markdown"
            )
            return
        
        # Procesar respuesta
        if context.user_data.get('buscador_esperando_respuesta'):
            secuencia_correcta = context.user_data.get('secuencia_actual', '')
            
            # Verificar formato básico
            if emblema_usuario in mensaje and '🧹' in mensaje and '🖐🏻' in mensaje and '🔅✊🏻' in mensaje:
                # Extraer flechas del mensaje
                flechas_map = {
                    '⬆️': '⬆️', '⬆': '⬆️', '↑': '⬆️',
                    '⬇️': '⬇️', '⬇': '⬇️', '↓': '⬇️',
                    '➡️': '➡️', '➡': '➡️', '→': '➡️',
                    '⬅️': '⬅️', '⬅': '⬅️', '←': '⬅️'
                }
                flechas_encontradas = []
                for char in mensaje:
                    normalizado = unicodedata.normalize('NFKC', char)
                    if normalizado in flechas_map:
                        flechas_encontradas.append(flechas_map[normalizado])
                    elif char in flechas_map:
                        flechas_encontradas.append(flechas_map[char])
                flechas_str = ''.join(flechas_encontradas)
                
                if flechas_str == secuencia_correcta:
                    # Captura exitosa
                    aciertos = context.user_data.get('buscador_aciertos', 0) + 1
                    restantes = context.user_data.get('buscador_snitches_restantes', 3) - 1
                    context.user_data['buscador_aciertos'] = aciertos
                    context.user_data['buscador_snitches_restantes'] = restantes
                    context.user_data['buscador_esperando_respuesta'] = False
                    
                    if restantes > 0:
                        await update.message.reply_text(
                            f"🎉 *¡SNITCH CAPTURADA!* 🎉\n\n"
                            f"✅ Secuencia correcta: {secuencia_correcta}\n"
                            f"✨ *Snitches restantes:* {restantes}/3\n\n"
                            f"⚡ *Escribe 'empezar' para la siguiente snitch.*",
                            parse_mode="Markdown"
                        )
                    else:
                        await update.message.reply_text(
                            f"🏆 *¡PRÁCTICA COMPLETADA!* 🏆\n\n"
                            f"✅ Capturaste las 3 snitches.\n"
                            f"📊 *Total de capturas:* {aciertos}/3\n\n"
                            f"🎉 ¡Excelente trabajo, buscador!\n\n"
                            f"Usa /practicar para volver a entrenar.",
                            parse_mode="Markdown"
                        )
                        context.user_data['practica_activa'] = None
                else:
                    # Captura fallida
                    fallos = context.user_data.get('buscador_fallos', 0) + 1
                    restantes = context.user_data.get('buscador_snitches_restantes', 3) - 1
                    context.user_data['buscador_fallos'] = fallos
                    context.user_data['buscador_snitches_restantes'] = restantes
                    context.user_data['buscador_esperando_respuesta'] = False
                    
                    if restantes > 0:
                        await update.message.reply_text(
                            f"❌ *¡SNITCH PERDIDA!* ❌\n\n"
                            f"Tu respuesta: {flechas_str}\n"
                            f"Secuencia correcta: {secuencia_correcta}\n"
                            f"✨ *Snitches restantes:* {restantes}/3\n\n"
                            f"⚡ *Escribe 'empezar' para la siguiente snitch.*",
                            parse_mode="Markdown"
                        )
                    else:
                        await update.message.reply_text(
                            f"💀 *PRÁCTICA TERMINADA* 💀\n\n"
                            f"No lograste capturar las 3 snitches.\n"
                            f"📊 *Snitches capturadas:* {context.user_data.get('buscador_aciertos', 0)}/3\n\n"
                            f"Usa /practicar para volver a intentarlo.",
                            parse_mode="Markdown"
                        )
                        context.user_data['practica_activa'] = None
            else:
                await update.message.reply_text(
                    f"❌ *Formato incorrecto.*\n\n"
                    f"📝 *Formato correcto:*\n"
                    f"`{emblema_usuario}🧹🖐🏻⬆️⬇️➡️⬅️🔅✊🏻`\n\n"
                    f"*Consejos:*\n"
                    f"• Usa tu emblema {emblema_usuario}\n"
                    f"• Incluye: 🧹 (escoba)\n"
                    f"• Incluye: 🖐🏻 (mano)\n"
                    f"• Secuencia de flechas\n"
                    f"• Termina con: 🔅✊🏻 (snitch capturada)\n\n"
                    f"Intenta de nuevo con la misma snitch:",
                    parse_mode="Markdown"
                )
            return
        
        # Si no está en estado activo
        await update.message.reply_text(
            f"🟣 *Práctica de Buscador*\n\n"
            f"Escribe *'empezar'* para comenzar.\n"
            f"Escribe *'salir'* para terminar.",
            parse_mode="Markdown"
        )            
    
    elif context.user_data.get('esperando_casa'):
        casa = update.message.text
        if casa in ["Galkin", "Darfor", "Olsson"]:
            user_id = update.effective_user.id
            nombre = update.effective_user.first_name
        
            # Convertir nombre de casa a emoji
            emblema_usuario = "❤️" if casa == "Galkin" else "💜" if casa == "Darfor" else "💚"
        
            conn = sqlite3.connect('quidditch.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usuarios (id_telegram, nombre, casa, emblema, cargo, puntos_totales, fecha_registro) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, nombre, casa, emblema_usuario, "Estudiante", 0, datetime.now())
            )
            conn.commit()
            conn.close()
        
            await update.message.reply_text(
                f"✅ ¡Cuenta creada!\n\n"
                f"Nombre: {nombre}\n"
                f"Casa: {casa} {emblema_usuario}\n"
                f"Cargo: Estudiante\n\n"
                "Ahora escribe /start para comenzar."
            )
            context.user_data['esperando_casa'] = False
        else:
            await update.message.reply_text("Casa no válida. Elige: Galkin, Darfor u Olsson")
    
    else:
        await update.message.reply_text("Usa /start para comenzar o /crear_cuenta para registrarte")

async def aprender(update, context):
    keyboard = [
        [InlineKeyboardButton("🟣 Buscador", callback_data="aprender_buscador"), InlineKeyboardButton("🔴 Cazador", callback_data="aprender_cazador")],
        [InlineKeyboardButton("🟡 Guardián", callback_data="aprender_guardian"), InlineKeyboardButton("🟢 Golpeador", callback_data="aprender_golpeador")],
        [InlineKeyboardButton("📜 Reglas generales", callback_data="aprender_general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📚 *CENTRO DE APRENDIZAJE*\n\nElige una opción:", reply_markup=reply_markup, parse_mode="Markdown")

async def boton_aprender(update, context):
    query = update.callback_query
    await query.answer()
    opcion = query.data

    textos = {
        "aprender_general": (
            "🏉 *REGLAS GENERALES* 🏉\n\n"
            "0. *Base:* Se sigan las normas generales del colegio durante el partido.\n\n"
            "1. *Puntos:* El valor de la snitch es de 150, de un gol de 100 y de un golpe efectivo 50.\n\n"
            "2. *Golpes efectivos:* 3 golpes efectivos a una misma persona lo saca del juego durante 5 minutos.\n\n"
            "3. *Cambios:* Los cambios se realizan al acabar una ronda y solo el capitán está autorizado a hacer cambios o hablar durante el partido.\n\n"
            "4. *Árbitro:* Solamente el árbitro está autorizado a detener el partido o mandar multimedia, para hablar con el árbitro se debe etiquetar a este en el partido una vez haya finalizado una ronda y solo puede ser el capitán, ya sea para corregir algún error o para un cambio.\n\n"
            "5. *Suplentes:* Cada equipo podrá contar con un máximo de 4 suplentes.\n\n"
            "6. *Participantes:* En caso de la ausencia de algún participante a la hora de comenzar el partido tendrán 2 minutos para decidir y realizar un cambio o el partido comenzará a pesar de que falte alguien.\n\n"
            "7. *Default:* Un equipo titular que le falten 3 integrantes perderá por default, esto también ocurrirá en caso de que no se presenten al partido, el default dará al equipo contrario los puntos de las 3 snitch y el equipo que no se presentó se llevará una penalización de puntos y galeones para su casa.\n\n"
            "8. *Amonestaciones:* El incumplimiento de alguna de las reglas puede ser penalizado de 3 formas, tarjeta amarilla de advertencia (amonestación leve), tarjeta roja de expulsión (amonestación fuerte), tarjeta negra de expulsión y pérdida de puntos (amonestación grave), un participante expulsado deja a su equipo con 1 de menos durante 10 minutos y no puede volver a jugar ese partido.\n\n"
            "9. *Vacío legal:* En caso de vacío legal o inconsistencia de alguna regla o norma el árbitro tendrá potestad total para tomar la decisión que crea correspondiente."
        ),
        "aprender_cazador": (
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰\n\n"
            "*CAZADOR* 🏉\n\n"
            "📌 *FUNCIÓN:* Los cazadores tendrán la tarea de pasarse la quaffle entre ellos y tirar a los aros para intentar anotar al contrario.\n\n"
            "🔄 *FORMATO DE PASE:*\n"
            "`[Emblema]🏉@cazador`\n"
            "💡 *Ejemplo:* `🤍🏉@cazador`\n\n"
            "🎯 *FORMATO DE DISPARO:*\n"
            "`[Emblema]🏉[Aro][3 números]`\n"
            "💡 *Ejemplo:* `🤍🏉🅱️3️⃣7️⃣1️⃣`\n\n"
            "⚡ *PENALES:*\n"
            "`[Emblema]🏉[Aro][6 números]`\n"
            "💡 *Ejemplo:* `🤍🏉🅱️5️⃣2️⃣1️⃣7️⃣8️⃣4️⃣`\n\n"
            "⭕ *REGLAS:*\n"
            "• Estarán en juego un total de 3 cazadores con su respectivo suplente.\n"
            "• Deben realizar un mínimo de 4 pases y un máximo de 10 sin omitir a ningún cazador antes de disparar a los aros.\n"
            "• En caso de fallar en la utilización de cualquier emoji, el árbitro cantará penal para el equipo contrario que cometió el error, eligiendo también que cazador será el encargado de disparar.\n"
            "• La omisión de alguno, el exceso o falta de pases harán que el equipo poseedor del balón pierda la quaffle y pase instantáneamente al guardián del equipo contrario el cuál tendrá la misión de pasarla a sus cazadores.\n\n"
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰"
        ),
        "aprender_guardian": (
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰\n\n"
            "*GUARDIÁN* 🧹\n\n"
            "📌 *FUNCIÓN:* El guardián debe dar todo de sí y tener la habilidad suficiente para ser capaz de ir hacia cualquiera de los tres aros y defenderlo evitando el tiro.\n\n"
            "📊 *TABLA PARA DEFENDER DISPAROS:*\n"
            "• (2️⃣5️⃣1️⃣) → 🧹⬅️\n"
            "• (8️⃣9️⃣3️⃣) → 🧹⬆️\n"
            "• (7️⃣4️⃣6️⃣) → 🧹➡️\n\n"
            "📝 *NOTA:* Esta tabla el Guardián oficial se la debe aprender para el torneo de quidditch.\n\n"
            "🎯 *EJEMPLO DE DISPARO:*\n"
            "`🤍🏉🅰️3️⃣7️⃣1️⃣`\n\n"
            "🛡️ *DEFENSA DEL GUARDIÁN:*\n"
            "`🤍🧹🅰️⬆️➡️⬅️`\n\n"
            "⚡ *PENALES:*\n"
            "Un cazador realizará un disparo a cualquiera de los aros de 6 combinaciones de números.\n\n"
            "💡 *Ejemplo de disparo de penal:*\n"
            "`🤍🏉🅾️4️⃣2️⃣8️⃣1️⃣9️⃣7️⃣`\n\n"
            "🛡️ *Defensa para penal:*\n"
            "`🤍🧹🅾️➡️⬅️⬆️⬅️⬆️➡️`\n\n"
            "⭕ *REGLAS:*\n"
            "• Cualquier fallo tanto en combinación como en emojis a la hora de defender será considerado tiro efectivo.\n"
            "• Tendrá un máximo de 5 segundos para efectuar la correcta defensa.\n\n"
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰"
        ),
        "aprender_golpeador": (
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰\n\n"
            "*GOLPEADOR* 🏏\n\n"
            "📌 *FUNCIÓN:* Será un golpeador que contará con la misión de golpear a tanto cazadores como al guardián del equipo contrario y a su vez defender a su equipo de los golpes.\n\n"
            "⚔️ *FORMATO DE GOLPE:*\n"
            "`[Emblema]🏏💥[3 números]@cazador`\n"
            "💡 *Ejemplo:* `🤍🏏💥9️⃣5️⃣7️⃣@cazador`\n\n"
            "🛡️ *FORMATO DE DEFENSA:*\n"
            "`[Emblema]🧹[3 flechas según tabla]🏏❌`\n\n"
            "📊 *TABLA PARA DEFENDER GOLPES:*\n"
            "• (2️⃣5️⃣1️⃣) → 🧹⬅️\n"
            "• (8️⃣9️⃣3️⃣) → 🧹⬆️\n"
            "• (7️⃣4️⃣6️⃣) → 🧹➡️\n\n"
            "💡 *Ejemplo de defensa:*\n"
            "`🤍🧹⬆️⬅️➡️🏏❌`\n\n"
            "⭕ *REGLAS:*\n"
            "• Sólo tienen permitido golpear a los cazadores y al respectivo guardián del equipo contrario y cada golpeador podrá golpear una vez por ronda.\n"
            "• En caso de que el golpe al guardián sea efectivo y fuera efectuado durante el tiro al aro, si el golpeador contrario no defiende en el tiempo requerido (5 segundos) a pesar de la defensa del guardián se considerará un golpe especial que determinará un tiro efectivo a favor del equipo golpeador.\n"
            "• Cualquier mal uso de emojis a la hora de defender será considerado golpe efectivo.\n"
            "• Cualquier mal uso de emojis a la hora de golpear será detenido el partido y otorgando un penal al equipo contrario.\n\n"
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰"
        ),
        "aprender_buscador": (
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰\n\n"
            "*BUSCADOR* 🔅✊🏻\n\n"
            "📌 *FUNCIÓN:* El buscador no cuenta con un tiempo de reacción limitado, aparecerán un total de tres snitches durante todo el partido, debe estar atento en todo momento pues no sabrá donde ni cuando pueda aparecer la escurridiza snitch.\n\n"
            "✨ *MECÁNICA:*\n"
            "Durante cualquier momento del partido el moderador (bot) pondrá una combinación de direcciones (de 6 a 10) que seguirá la snitch al azar y ambos buscadores deberán reproducirlos con sus flechas respectivamente.\n\n"
            "📝 *Ejemplo de combinación:*\n"
            "`🔅ARRIBA/ABAJO/DERECHA/IZQUIERDA/ARRIBA/ARRIBA/ABAJO`\n\n"
            "🔍 *Formato de respuesta del buscador:*\n"
            "`[Emblema][Escoba][🖐🏻][🔅✊🏻][secuencia de flechas]`\n\n"
            "💡 *Ejemplo:*\n"
            "`🤍🧹🖐🏻⬆️⬇️➡️⬅️⬆️⬆️⬇️🔅✊🏻`\n\n"
            "🏆 *Gana la snitch* el buscador que atrape más rápido y bien la snitch.\n\n"
            "🏰💫🏰💫🏰💫🏰💫🏰💫🏰"
        ),
    }

    texto = textos.get(opcion, "Opción no válida")

    # Botones de acción al final
    keyboard = [
        [InlineKeyboardButton("🏋️ Ir a practicar", callback_data="ir_a_practicar")],
        [InlineKeyboardButton("📚 Regresar al menú", callback_data="regresar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        texto,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def ir_a_practicar(update, context):
    query = update.callback_query
    await query.answer()
    
    # Redirigir al menú de practicar
    keyboard = [
        [InlineKeyboardButton("🔴 Cazador", callback_data="prac_cazador"), InlineKeyboardButton("🟡 Guardián", callback_data="prac_guardian")],
        [InlineKeyboardButton("🟢 Golpeador", callback_data="prac_golpeador"), InlineKeyboardButton("🟣 Buscador", callback_data="prac_buscador")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🏋️ *MODO PRACTICAR* 🏋️\n\nElige la posición que quieres entrenar:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def regresar_menu(update, context):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🟣 Buscador", callback_data="aprender_buscador"), InlineKeyboardButton("🔴 Cazador", callback_data="aprender_cazador")],
        [InlineKeyboardButton("🟡 Guardián", callback_data="aprender_guardian"), InlineKeyboardButton("🟢 Golpeador", callback_data="aprender_golpeador")],
        [InlineKeyboardButton("📜 Reglas generales", callback_data="aprender_general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📚 *CENTRO DE APRENDIZAJE*\n\nElige una opción:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar(update, context):
    keyboard = [
        [InlineKeyboardButton("🔴 Cazador", callback_data="prac_cazador"), InlineKeyboardButton("🟡 Guardián", callback_data="prac_guardian")],
        [InlineKeyboardButton("🟢 Golpeador", callback_data="prac_golpeador"), InlineKeyboardButton("🟣 Buscador", callback_data="prac_buscador")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏋️ *MODO PRACTICAR*\n\nElige una posición:", reply_markup=reply_markup, parse_mode="Markdown")

async def practicar_cazador(update, context):
    query = update.callback_query
    await query.answer()
    
    context.user_data['practica_activa'] = 'cazador'
    context.user_data['pases_cazador'] = 0
    context.user_data['pases_realizados'] = []
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔴 *PRÁCTICA DE CAZADOR* 🔴\n\n"
        "📌 *Objetivo:* Realiza 4 pases y luego dispara.\n\n"
        "📝 *Formato de pase:*\n"
        "`🤍🏉@cazador2`\n"
        "(Reemplaza 'cazador2' con el nombre del usuario)\n\n"
        "🎯 *Formato de disparo:*\n"
        "`🤍🏉🅰️123`\n"
        "(Reemplaza '🅰️' por 🅰️, 🅱️ u 🅾️)\n\n"
        "💡 *Ejemplo de pase:* `🤍🏉@cazador2`\n"
        "💡 *Ejemplo de disparo:* `🤍🏉🅰️123`\n\n"
        "⚡ *Escribe 'salir' para terminar.*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_guardian(update, context):
    print("🟢 DEBUG: Entré a practicar_guardian")
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id

    # Obtener la casa del usuario desde la base de datos
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute("SELECT casa, emblema FROM usuarios WHERE id_telegram = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()

    casa_usuario = resultado[0] if resultado else "Galkin"  # Texto: "Galkin", "Darfor", "Olsson"
    emblema_usuario = resultado[1] if resultado else "❤️"   # Emoji: "❤️", "💜", "💚"

    # Guardar ambos en el contexto
    context.user_data['casa_usuario'] = casa_usuario
    context.user_data['emblema_usuario'] = emblema_usuario
    
    # Guardar que el usuario está en práctica de guardián
    context.user_data['practica_activa'] = 'guardian'
    context.user_data['guardian_aciertos'] = 0
    context.user_data['guardian_fallos'] = 0
    context.user_data['guardian_esperando_listo'] = True  # Esperando confirmación
    context.user_data['guardian_esperando_defensa'] = False
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Mostrar la casa que debe usar
    await query.edit_message_text(
        "🟡 *PRÁCTICA DE GUARDIÁN* 🟡\n\n"
        f"🏠 *Tu casa:* {emblema_usuario}{casa_usuario}\n"
        "📌 *Recuerda usar siempre tu emblema en la defensa.*\n\n"
        "📊 *TABLA DE NÚMEROS A FLECHAS:*\n"
        "(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️\n\n"
        "📝 *Formato de defensa:*\n"
        f"`{emblema_usuario}🧹[Aro][3 flechas]`\n\n"
        "💡 *Ejemplo:*\n"
        "Si el disparo es: `🤍🏉🅰️123`\n"
        f"La defensa correcta en tu caso sería: `{emblema_usuario}🧹🅰️⬅️⬅️⬆️`\n\n"
        "⚡ *Variantes permitidas:*\n"
        "• Aros: `🅰️` | `🅱️` | `🅾️`\n"
        "• Flechas: `⬅️`, `⬆️`, `➡️`\n\n"
        "⚡ *Escribe 'Si' cuando estés listo.*\n"
        "⚡ *Escribe 'Salir' para terminar.*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_golpeador(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute("SELECT casa, emblema FROM usuarios WHERE id_telegram = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    casa_usuario = resultado[0] if resultado else "Galkin"
    emblema_usuario = resultado[1] if resultado else "❤️"
    
    context.user_data['casa_usuario'] = casa_usuario
    context.user_data['emblema_usuario'] = emblema_usuario
    context.user_data['practica_activa'] = 'golpeador'
    context.user_data['golpeador_aciertos'] = 0
    context.user_data['golpeador_fallos'] = 0
    context.user_data['golpeador_modo'] = None
    context.user_data['golpeador_esperando'] = False
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟢 *PRÁCTICA DE GOLPEADOR* 🟢\n\n"
        f"🏠 *Tu casa:* {emblema_usuario} {casa_usuario}\n\n"
        "📊 *TABLA DE NÚMEROS A FLECHAS (para defender):*\n"
        "(2️⃣5️⃣1️⃣) → ⬅️\n(8️⃣9️⃣3️⃣) → ⬆️\n(7️⃣4️⃣6️⃣) → ➡️\n\n"
        "⚔️ *PARA ATACAR:*\n"
        f"`{emblema_usuario}🏏💥[3 números]@Usuario`\n"
        "💡 *Ejemplo:* `🤍🏏💥123@Usuario`\n\n"
        "🛡️ *PARA DEFENDER:*\n"
        f"`{emblema_usuario}🧹[3 flechas]🏏❌`\n"
        "💡 *Ejemplo:* `🤍🧹⬅️⬆️➡️🏏❌`\n\n"
        "⚡ *Escribe 'atacar' para golpear al bot.*\n"
        "⚡ *Escribe 'defender' para que el bot te ataque.*\n"
        "⚡ *Escribe 'salir' para terminar.*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_buscador(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Obtener datos del usuario
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute("SELECT casa, emblema FROM usuarios WHERE id_telegram = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    casa_usuario = resultado[0] if resultado else "Galkin"
    emblema_usuario = resultado[1] if resultado else "❤️"
    
    context.user_data['casa_usuario'] = casa_usuario
    context.user_data['emblema_usuario'] = emblema_usuario
    context.user_data['practica_activa'] = 'buscador'
    context.user_data['buscador_aciertos'] = 0
    context.user_data['buscador_fallos'] = 0
    context.user_data['buscador_snitches_restantes'] = 3
    context.user_data['buscador_esperando_respuesta'] = False
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟣 *PRÁCTICA DE BUSCADOR* 🟣\n\n"
        f"🏠 *Tu casa:* {emblema_usuario} {casa_usuario}\n\n"
        "📌 *OBJETIVO:* Captura las 3 snitches.\n\n"
        "✨ *MECÁNICA:*\n"
        "• El bot mostrará una combinación de *PALABRAS*:\n"
        "  `ARRIBA`, `ABAJO`, `DERECHA`, `IZQUIERDA`\n\n"
        "• Debes responder con *FLECHAS*:\n"
        "  `⬆️` (ARRIBA) | `⬇️` (ABAJO) | `➡️` (DERECHA) | `⬅️` (IZQUIERDA)\n\n"
        "📝 *Formato de respuesta:*\n"
        f"`{emblema_usuario}🧹🖐🏻[secuencia de flechas]🔅✊🏻`\n\n"
        "💡 *Ejemplo:*\n"
        "Si el bot muestra: `ARRIBA/ABAJO/IZQUIERDA/DERECHA`\n"
        f"Tu respuesta: `{emblema_usuario}🧹🖐🏻🔅✊🏻⬆️⬇️⬅️➡️`\n\n"
        "⚡ *Escribe 'empezar' para comenzar.*\n"
        "⚡ *Escribe 'salir' para terminar.*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def salir_practica(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['practica_activa'] = None
    await query.edit_message_text("✅ Has salido del modo práctica.")

async def ir_a_jugar(update, context):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🏆 *MODO JUGAR* 🏆\n\n"
        "Para iniciar una partida, el bot debe estar en un grupo.\n\n"
        "Comandos disponibles:\n"
        "/iniciar_partida - Comenzar una nueva partida\n"
        "/unirse - Unirse a una partida existente\n\n"
        "⚠️ Esta función estará disponible próximamente.",
        parse_mode="Markdown"
    )

async def boton_crear_cuenta(update, context):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("❤️ Galkin", callback_data="casa_Galkin")],
        [InlineKeyboardButton("💜 Darfor", callback_data="casa_Darfor")],
        [InlineKeyboardButton("💚 Olsson", callback_data="casa_Olsson")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Vamos a crear tu cuenta.\n\n"
        "Elige tu casa tocando un botón:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def boton_modificar_cuenta(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute("SELECT casa, emblema FROM usuarios WHERE id_telegram = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado is None:
        await query.edit_message_text(
            "❌ No tienes una cuenta activa.\n"
            "Usa /crear_cuenta para registrarte.",
            parse_mode="Markdown"
        )
        return
    
    casa_actual = resultado[0]
    emblema_actual = resultado[1]
    
    keyboard = [
        [InlineKeyboardButton("❤️ Cambiar a Galkin", callback_data="cambiar_casa_Galkin")],
        [InlineKeyboardButton("💜 Cambiar a Darfor", callback_data="cambiar_casa_Darfor")],
        [InlineKeyboardButton("💚 Cambiar a Olsson", callback_data="cambiar_casa_Olsson")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cambio")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔧 *Modificar cuenta*\n\n"
        f"Casa actual: {emblema_actual} {casa_actual}\n\n"
        f"¿A qué casa quieres cambiarte?\n\n"
        f"*Nota:* Al cambiar de casa, tus estadísticas se mantienen.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def cambiar_casa(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    nueva_casa = query.data.replace("cambiar_casa_", "")  # Galkin, Darfor, Olsson
    
    # Convertir nombre a emoji
    nuevo_emblema = "❤️" if nueva_casa == "Galkin" else "💜" if nueva_casa == "Darfor" else "💚"
    
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET casa = ?, emblema = ? WHERE id_telegram = ?",
        (nueva_casa, nuevo_emblema, user_id)
    )
    conn.commit()
    conn.close()
    
    await query.edit_message_text(
        f"✅ *Casa actualizada correctamente*\n\n"
        f"Ahora perteneces a {nuevo_emblema} {nueva_casa}.\n\n"
        f"Usa /start para ver el menú principal.",
        parse_mode="Markdown"
    )

async def cancelar_cambio(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ Cambio cancelado. Tu casa sigue igual.\n\n"
        "Usa /start para volver al menú.",
        parse_mode="Markdown"
    )

async def ir_a_aprender(update, context):
    query = update.callback_query
    await query.answer()
    
    # Llamar directamente a la función aprender
    keyboard = [
        [InlineKeyboardButton("🟣 Buscador", callback_data="aprender_buscador"), InlineKeyboardButton("🔴 Cazador", callback_data="aprender_cazador")],
        [InlineKeyboardButton("🟡 Guardián", callback_data="aprender_guardian"), InlineKeyboardButton("🟢 Golpeador", callback_data="aprender_golpeador")],
        [InlineKeyboardButton("📜 Reglas generales", callback_data="aprender_general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📚 *CENTRO DE APRENDIZAJE*\n\nElige una opción:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def seleccionar_casa(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    nombre = update.effective_user.first_name
    
    # Obtener la casa seleccionada
    casa = query.data.replace("casa_", "")  # Galkin, Darfor, Olsson
    
    # Convertir nombre de casa a emoji
    emblema_usuario = "❤️" if casa == "Galkin" else "💜" if casa == "Darfor" else "💚"
    
    # Guardar en la base de datos
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usuarios (id_telegram, nombre, casa, emblema, cargo, puntos_totales, fecha_registro) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, nombre, casa, emblema_usuario, "Estudiante", 0, datetime.now())
    )
    conn.commit()
    conn.close()
    
    # Mostrar mensaje de éxito con botones
    keyboard = [
        [InlineKeyboardButton("🏋️ Practicar", callback_data="ir_a_practicar")],
        [InlineKeyboardButton("📚 Aprender", callback_data="ir_a_aprender")],
        [InlineKeyboardButton("🏆 Jugar", callback_data="ir_a_jugar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ *¡Cuenta creada!*\n\n"
        f"Nombre: {nombre}\n"
        f"Casa: {emblema_usuario} {casa}\n"
        f"Cargo: Estudiante\n\n"
        "¿Qué deseas hacer?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ============= INICIAR EL BOT =============
def main():
    iniciar_bd()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crear_cuenta", crear_cuenta))
    app.add_handler(CommandHandler("aprender", aprender))
    app.add_handler(CommandHandler("practicar", practicar))
    app.add_handler(CommandHandler("jugar", jugar))
    
    app.add_handler(CallbackQueryHandler(practicar_cazador, pattern="prac_cazador"))
    app.add_handler(CallbackQueryHandler(practicar_guardian, pattern="prac_guardian"))
    app.add_handler(CallbackQueryHandler(practicar_golpeador, pattern="prac_golpeador"))
    app.add_handler(CallbackQueryHandler(practicar_buscador, pattern="prac_buscador"))
    app.add_handler(CallbackQueryHandler(salir_practica, pattern="salir_practica"))
    app.add_handler(CallbackQueryHandler(boton_aprender, pattern="aprender_"))
    app.add_handler(CallbackQueryHandler(ir_a_practicar, pattern="ir_a_practicar"))
    app.add_handler(CallbackQueryHandler(regresar_menu, pattern="regresar"))
    app.add_handler(CallbackQueryHandler(boton_crear_cuenta, pattern="crear_cuenta"))
    app.add_handler(CallbackQueryHandler(boton_modificar_cuenta, pattern="modificar_cuenta"))
    app.add_handler(CallbackQueryHandler(cambiar_casa, pattern="cambiar_casa_"))
    app.add_handler(CallbackQueryHandler(cancelar_cambio, pattern="cancelar_cambio"))
    app.add_handler(CallbackQueryHandler(ir_a_aprender, pattern="ir_a_aprender"))
    app.add_handler(CallbackQueryHandler(ir_a_practicar, pattern="ir_a_practicar"))
    app.add_handler(CallbackQueryHandler(ir_a_jugar, pattern="ir_a_jugar"))
    app.add_handler(CallbackQueryHandler(seleccionar_casa, pattern="casa_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensajes))
    
    print("🐲 Bot de Quidditch iniciado...")
    
    threading.Thread(target=run_web).start()
    app.run_polling()

if __name__ == "__main__":
    main()