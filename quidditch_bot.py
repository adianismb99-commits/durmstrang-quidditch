import json
import os
import sqlite3
import asyncio
import threading
import re
from datetime import datetime
from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton
from flask import Flask
from supabase import create_client, Client
from dotenv import load_dotenv
load_dotenv()  # <-- Esto lee el archivo .env y crea las variables de entorno

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ Faltan variables SUPABASE_URL o SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def defensa_numero(numero):
    tabla = {
        '1': '⬅️', '2': '⬅️', '3': '⬆️',
        '4': '➡️', '5': '⬅️', '6': '➡️',
        '7': '➡️', '8': '⬆️', '9': '⬆️'
    }
    return tabla.get(numero, '❌')

# === SERVICIO WEB PARA KEEP-ALIVE ===
app = Flask(__name__)

@app.route('/')
def health_check():
    # Esta es la respuesta simple que cron-job.org verá
    return "OK", 200

def run_web():
    import os
    port = int(os.environ.get('PORT', 10000))
    for p in [port, 10001, 10002, 10003]:
        try:
            app.run(host='0.0.0.0', port=p, use_reloader=False)  # Cambiado a 'app'
            break
        except OSError:
            print(f"Puerto {p} ocupado, intentando con el siguiente...")
            continue

# === CONFIGURACION ===
# Toma el token de las variables de entorno del sistema.
# Es mucho más seguro y necesario para Render.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8840107743:AAFNg1W9aSNMH_4vxYyPUfFFHgsCfYMsJZA")
if not TOKEN:
    TOKEN = "8840107743:AAFNg1W9aSNMH_4vxYyPUfFFHgsCfYMsJZA"

# ============= BASE DE DATOS =============

def iniciar_bd():
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    
    # Tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_telegram INTEGER PRIMARY KEY,
            nombre TEXT,
            casa TEXT,
            cargo TEXT,
            puntos_totales INTEGER DEFAULT 0,
            fecha_registro TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# ============= COMANDOS =============
async def start(update, context):
    user_id = update.effective_user.id
    nombre = update.effective_user.first_name
    
    conn = sqlite3.connect('quidditch.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM usuarios WHERE id_telegram = ?", (user_id,))
    usuario = cursor.fetchone()
    conn.close()
    
    if usuario is None:
        # Usuario nuevo: pedir crear cuenta
        await update.message.reply_text(
            f"✨ ¡Bienvenido {nombre} al Quidditch Emoji Bot! ✨\n\n"
            "Para comenzar, necesitas crear una cuenta.\n\n"
            "Comando: /crear_cuenta\n\n"
            "Serás parte de una de las tres casas mágicas: Galkin ❤️, Darfor 💜 u Olsson 💚"
        )
    else:
        # Usuario existente
        await update.message.reply_text(
            f"¡Bienvenido de vuelta {usuario[1]}!\n"
            f"Casa: {usuario[2]}\n"
            f"Cargo: {usuario[3]}\n\n"
            "¿Qué deseas hacer?\n"
            "/practicar - Entrenar una posición\n"
            "/jugar - Iniciar una partida\n"
            "/aprender - Ver reglas del juego"
        )

async def crear_cuenta(update, context):
    # Aquí implementaremos el registro
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
    # Verificar si el usuario está en modo práctica
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
        
        # Verificar si es un pase
        if '🏉' in mensaje and '@' in mensaje:
            context.user_data['pases_cazador'] += 1
            context.user_data['pases_realizados'].append(mensaje)
            pases_actuales = context.user_data['pases_cazador']
            
            if pases_actuales < 4:
                await update.message.reply_text(
                    f"✅ Pase correcto. Llevas {pases_actuales}/4 pases.\n"
                    f"Sigue pasando la Quaffle. (máximo 10 pases)"
                )
            elif 4 <= pases_actuales <= 10:
                await update.message.reply_text(
                    f"✅ Pase correcto. Llevas {pases_actuales} pases.\n\n"
                    f"🎯 ¡Ya puedes disparar! Usa el formato:\n"
                    f"`❤️🏉🅰️123`\n\n"
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
        elif '🏉' in mensaje and ('🅰️' in mensaje or '🅱️' in mensaje or '🅾️' in mensaje):
            pases = context.user_data.get('pases_cazador', 0)
        
            if pases < 4:
                await update.message.reply_text(
                    f"❌ No puedes disparar todavía. Llevas solo {pases}/4 pases.\n"
                    f"Completa los pases mínimos primero."
                )
            else:
                # Extraer números (acepta 1,2,3 en lugar de 1️⃣,2️⃣,3️⃣)
                numeros = re.findall(r'[1-9]', mensaje)
            
                if len(numeros) == 3:
                    flechas = ''.join([defensa_numero(n) for n in numeros])
                
                    # Detectar qué aro usó
                    aro = None
                    if '🅰️' in mensaje:
                        aro = '🅰️'
                    elif '🅱️' in mensaje:
                        aro = '🅱️'
                    elif '🅾️' in mensaje:
                        aro = '🅾️'
                
                    # Detectar qué casa usó
                    casa = "❤️" if '❤️' in mensaje else "💜" if '💜' in mensaje else "💚" if '💚' in mensaje else "?"
                
                    await update.message.reply_text(
                        f"🎯 ¡Disparo realizado!\n"
                        f"Casa: {casa} | Aro: {aro}\n"
                        f"Números: {''.join(numeros)}\n\n"
                        f"🟡 Defensa del guardián: {flechas}\n\n"
                        f"✅ ¡GOL! +10 puntos"
                    )
                
                    # Reiniciar práctica
                    context.user_data['pases_cazador'] = 0
                    context.user_data['pases_realizados'] = []
                else:
                    await update.message.reply_text(
                        f"❌ Disparo inválido. Debes usar EXACTAMENTE 3 números (1-9).\n"
                        f"Ejemplo: `❤️🏉🅰️123`\n"
                        f"Tú usaste {len(numeros)} números: {''.join(numeros) if numeros else 'ninguno'}"
                    )
        
        else:
            await update.message.reply_text(
                f"❌ Formato no reconocido.\n\n"
                f"📝 **Formato de pase:**\n"
                f"`❤️🏉@cazador2`\n\n"
                f"🎯 **Formato de disparo:**\n"
                f"`❤️🏉🅰️123`\n\n"
                f"Escribe 'salir' para terminar."
            )
    
    elif practica == 'guardian':
        mensaje = update.message.text
        if mensaje.lower() == 'salir':
            context.user_data['practica_activa'] = None
            await update.message.reply_text("✅ Práctica de Guardián finalizada. Usa /practicar para volver.")
            return
        
        await update.message.reply_text(f"🛡️ Defensa recibida: {mensaje}\n\n(Ejercicio de Guardián en desarrollo)")
    
    elif practica == 'golpeador':
        mensaje = update.message.text
        if mensaje.lower() == 'salir':
            context.user_data['practica_activa'] = None
            await update.message.reply_text("✅ Práctica de Golpeador finalizada. Usa /practicar para volver.")
            return
        
        await update.message.reply_text(f"⚔️ Acción recibida: {mensaje}\n\n(Ejercicio de Golpeador en desarrollo)")
    
    elif practica == 'buscador':
        mensaje = update.message.text
        if mensaje.lower() == 'salir':
            context.user_data['practica_activa'] = None
            await update.message.reply_text("✅ Práctica de Buscador finalizada. Usa /practicar para volver.")
            return
        
        await update.message.reply_text(f"🔍 Secuencia recibida: {mensaje}\n\n(Ejercicio de Buscador en desarrollo)")
    
    elif context.user_data.get('esperando_casa'):
        casa = update.message.text
        if casa in ["Galkin", "Darfor", "Olsson"]:
            user_id = update.effective_user.id
            nombre = update.effective_user.first_name
            
            data = {
                "id_telegram": user_id,
                "nombre": nombre,
                "casa": casa,
                "cargo": "Estudiante",
                "puntos_totales": 0,
                "fecha_registro": datetime.now().isoformat()
            }
            supabase.table('usuarios').insert(data).execute()
            
            await update.message.reply_text(
                f"✅ ¡Cuenta creada!\n\n"
                f"Nombre: {nombre}\n"
                f"Casa: {casa}\n"
                f"Cargo: Estudiante\n\n"
                "Ahora puedes usar:\n"
                "/practicar - Entrenar\n"
                "/jugar - Partidas\n"
                "/aprender - Reglas"
            )
            context.user_data['esperando_casa'] = False
        else:
            await update.message.reply_text("Casa no válida. Elige: Galkin, Darfor u Olsson")
    
    else:
        await update.message.reply_text("Usa /start para comenzar o /crear_cuenta para registrarte")

async def aprender(update, context):
    keyboard = [
        [
            InlineKeyboardButton("📜 Reglas generales", callback_data="aprender_general"),
            InlineKeyboardButton("🔴 Cazador", callback_data="aprender_cazador")
        ],
        [
            InlineKeyboardButton("🟡 Guardián", callback_data="aprender_guardian"),
            InlineKeyboardButton("🟢 Golpeador", callback_data="aprender_golpeador")
        ],
        [
            InlineKeyboardButton("🟣 Buscador", callback_data="aprender_buscador"),
            InlineKeyboardButton("⚡ Práctica rápida", callback_data="aprender_practica")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📚 *CENTRO DE APRENDIZAJE* 📚\n\nElige una opción:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def boton_aprender(update, context):
    query = update.callback_query
    print(f"🔘 boton_aprender recibió: {query.data}")  # ← Línea de debug
    await query.answer()
    
    opcion = query.data
    
    if opcion == "aprender_general":
        texto = (
            "📜 *REGLAS GENERALES DEL QUIDDITCH EMOJI* 📜\n\n"
            "🎯 *OBJETIVO:* Ganar más puntos que el equipo contrario.\n\n"
            "⚡ *PUNTUACIÓN:*\n"
            "• Gol en los aros: 10 puntos\n"
            "• Capturar Snitch: 150 puntos\n\n"
            "🔄 *DESARROLLO:*\n"
            "• 3 snitches por partido\n"
            "• El partido termina cuando se capturan las 3\n\n"
            "🏆 *GANADOR:* El equipo con más puntos al final."
        )
    elif opcion == "aprender_cazador":
        texto = (
            "🔴 *CAZADOR* 🔴\n\n"
            "📌 *FUNCIÓN:* Anotar goles en los aros contrarios.\n\n"
            "🔄 *PASES:*\n"
            "• Formato: [Casa]🏉@cazador\n"
            "• Ejemplo: ❤️🏉@cazador2\n"
            "• Mínimo 4 pases, máximo 10\n"
            "• No se puede omitir a ningún cazador\n\n"
            "🎯 *DISPARO:*\n"
            "• Formato: `[Casa]🏉[Aro][3 números]`\n"
            "• Ejemplo: ❤️🏉🅱️3️⃣7️⃣1️⃣\n\n"
            "❌ *FALLOS:* Penal o pérdida de la Quaffle"
        )
    elif opcion == "aprender_guardian":
        texto = (
            "🟡 *GUARDIÁN* 🟡\n\n"
            "📌 *FUNCIÓN:* Defender los aros y evitar goles.\n\n"
            "🛡️ *DEFENSA:*\n"
            "• Tienes 5 segundos para responder\n"
            "• Formato: `[Casa]🧹[Aro][3 flechas]`\n\n"
            "• Ejemplo: ❤️🧹🅱️⬅️⬆️➡️\n\n"
            "📊 *TABLA DE NÚMEROS A FLECHAS:*\n"
            "1⬅️ 2⬅️ 3⬆️ 4➡️ 5⬅️ 6➡️ 7➡️ 8⬆️ 9⬆️\n\n"
            "• Combinaciones clave:\n"
            "  251 = ⬅️ | 893 = ⬆️ | 746 = ➡️\n\n"
            "❌ *SI FALLAS:* Gol efectivo"
        )
    elif opcion == "aprender_golpeador":
        texto = (
            "🟢 *GOLPEADOR* 🟢\n\n"
            "📌 *FUNCIÓN:* Golpear rivales y defender a tu equipo.\n\n"
            "⚔️ *GOLPE:*\n"
            "• Formato: `[Casa]🏏💥[3 números]@rival`\n"
            "• Ejemplo: ❤️🏏💥3️⃣7️⃣1️⃣\n\n"
            "• 1 golpe por ronda\n\n"
            "🛡️ *DEFENSA:*\n"
            "• Formato: `[Casa]🧹[3 flechas]🏏❌`\n"
            "• Ejemplo: ❤️🧹⬅️⬆️➡️🏏❌\n\n"
            "• Tienes 5 segundos para defender\n\n"
            "💥 *GOLPE EFECTIVO:* Rival fuera 20 segundos\n"
            "🎯 *GOLPE ESPECIAL:* Al guardián durante tiro = gol automático"
        )
    elif opcion == "aprender_buscador":
        texto = (
            "🟣 *BUSCADOR* 🟣\n\n"
            "📌 *FUNCIÓN:* Capturar la Snitch.\n\n"
            "✨ *MECÁNICA:*\n"
            "• Aparecen 3 snitches por partido\n"
            "• El bot muestra una secuencia de 6-10 direcciones\n\n"
            "• Moderador: ARRIBA|ABAJO|DERECHA|IZQUIERDA|ARRIBA|ABAJO\n"
            "🔍 *RESPUESTA:*\n"
            "• Formato: `[Casa]🧹🖐🏻[secuencia flechas]🔅✊🏻`\n"
            "• Ejemplo: ❤️🧹🖐🏻⬆️⬇️⬅️➡️⬆️⬇️🔅✊🏻\n\n"
            "• Gana la snitch el que responda más rápido y correcto\n\n"
            "⚠️ *SI FALLAS:* Pierdes esa snitch"
        )
    elif opcion == "aprender_practica":
        texto = (
            "⚡ *PRÁCTICA RÁPIDA* ⚡\n\n"
            "Próximamente tendrás ejercicios interactivos para:\n\n"
            "• Practicar disparos como Cazador\n"
            "• Entrenar defensas como Guardián\n"
            "• Mejorar reflejos como Buscador\n"
            "• Golpear rivales como Golpeador\n\n"
            "¡Prepárate para convertirte en un maestro del Quidditch!"
        )
    else:
        texto = "Opción no válida."
    
    await query.edit_message_text(
        texto,
        parse_mode="Markdown"
    )

async def practicar(update, context):
    keyboard = [
        [
            InlineKeyboardButton("🔴 Cazador", callback_data="prac_cazador"),
            InlineKeyboardButton("🟡 Guardián", callback_data="prac_guardian")
        ],
        [
            InlineKeyboardButton("🟢 Golpeador", callback_data="prac_golpeador"),
            InlineKeyboardButton("🟣 Buscador", callback_data="prac_buscador")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏋️ *MODO PRACTICAR* 🏋️\n\nElige la posición que quieres entrenar:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_cazador(update, context):
    query = update.callback_query
    await query.answer()
    
    # Guardar que el usuario está en práctica de cazador
    context.user_data['practica_activa'] = 'cazador'
    context.user_data['pases_cazador'] = 0
    context.user_data['pases_realizados'] = []
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔴 *PRÁCTICA DE CAZADOR* 🔴\n\n"
        "Objetivo: Realiza 4 pases y luego dispara.\n\n"
        "📝 *Formato de pase:*\n"
        "`❤️🏉@usuario`\n\n"
        "🎯 *Formato de disparo:*\n"
        "`❤️🏉🅰️1️⃣2️⃣3️⃣`\n\n"
        "¡Comienza a practicar! Escribe tu primer pase.\n\n"
        "*(Escribe 'salir' en cualquier momento para terminar)*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    

async def practicar_guardian(update, context):
    query = update.callback_query
    await query.answer()
    
    context.user_data['practica_activa'] = 'guardian'
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟡 *PRÁCTICA DE GUARDIÁN* 🟡\n\n"
        "Te mostraré un disparo y debes defenderlo.\n\n"
        "📊 *Tabla de números a flechas:*\n"
        "1⬅️ 2⬅️ 3⬆️ 4➡️ 5⬅️ 6➡️ 7➡️ 8⬆️ 9⬆️\n\n"
        "📝 *Formato de defensa:*\n"
        "`❤️🧹🅰️⬆️⬅️➡️`\n\n"
        "¿Listo? Escribe 'empezar' para comenzar.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_golpeador(update, context):
    query = update.callback_query
    await query.answer()
    
    context.user_data['practica_activa'] = 'golpeador'
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟢 *PRÁCTICA DE GOLPEADOR* 🟢\n\n"
        "Objetivo: Golpea al rival y defiende sus golpes.\n\n"
        "⚔️ *Formato de golpe:*\n"
        "`❤️🏏💥1️⃣2️⃣3️⃣@rival`\n\n"
        "🛡️ *Formato de defensa:*\n"
        "`❤️🧹⬆️⬅️➡️🏏❌`\n\n"
        "Escribe 'golpear' para atacar o 'defender' para practicar defensa.\n\n"
        "*(Escribe 'salir' en cualquier momento para terminar)*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def practicar_buscador(update, context):
    query = update.callback_query
    await query.answer()
    
    context.user_data['practica_activa'] = 'buscador'
    
    keyboard = [[InlineKeyboardButton("❌ Salir de práctica", callback_data="salir_practica")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟣 *PRÁCTICA DE BUSCADOR* 🟣\n\n"
        "Aparecerá una secuencia de flechas que debes copiar.\n\n"
        "📝 *Formato de respuesta:*\n"
        "`❤️🧹🖐🏻🔅✊🏻⬆️⬇️➡️⬅️⬆️`\n\n"
        "Escribe 'empezar' para recibir tu primera secuencia.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def salir_practica(update, context):
    query = update.callback_query
    await query.answer()
    
    context.user_data['practica_activa'] = None
    await query.edit_message_text(
        "✅ Has salido del modo práctica.\n\n"
        "Usa /practicar cuando quieras volver a entrenar."
    )

async def jugar(update, context):
    await update.message.reply_text(
        "🏆 *MODO JUGAR* 🏆\n\n"
        "Para iniciar una partida, el bot debe estar en un grupo.\n\n"
        "Comandos disponibles:\n"
        "/iniciar_partida - Comenzar una nueva partida\n"
        "/unirse - Unirse a una partida existente\n\n"
        "⚠️ Esta función estará disponible próximamente."
    )

   

# ============= INICIAR EL BOT =============
def main():

    import sys
    import asyncio
    
    # Solo para Windows con Python 3.14+
    if sys.platform == "win32" and sys.version_info >= (3, 14):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except DeprecationWarning:
            pass  # Ignorar advertencia

    # Iniciar base de datos
    iniciar_bd()
    
    # Crear la aplicación
    app = Application.builder().token(TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crear_cuenta", crear_cuenta))
    app.add_handler(CommandHandler("aprender", aprender))      
    app.add_handler(CommandHandler("practicar", practicar))    
    app.add_handler(CommandHandler("jugar", jugar))            

    #Manejador de botones
    app.add_handler(CallbackQueryHandler(practicar_cazador, pattern="prac_cazador"))
    app.add_handler(CallbackQueryHandler(practicar_guardian, pattern="prac_guardian"))
    app.add_handler(CallbackQueryHandler(practicar_golpeador, pattern="prac_golpeador"))
    app.add_handler(CallbackQueryHandler(practicar_buscador, pattern="prac_buscador"))
    app.add_handler(CallbackQueryHandler(salir_practica, pattern="salir_practica"))
    app.add_handler(CallbackQueryHandler(boton_aprender, pattern="aprender_"))

    # Manejador de mensajes de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensajes))
     
    print("🐲 Bot de Quidditch iniciado...")
    
    # Inicia el servidor web en un hilo separado
    threading.Thread(target=run_web).start()
    
    app.run_polling()

if __name__ == "__main__":
#>>>>>>> 22b6683ae61f0cfdfd36d8bfd9f783e168acea0b
    main()