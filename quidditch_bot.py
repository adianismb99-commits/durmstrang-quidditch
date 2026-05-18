import os
import sqlite3
import asyncio
import threading
import re
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

# ============= FUNCIONES AUXILIARES =============
def defensa_numero(numero):
    tabla = {
        '1': '⬅️', '2': '⬅️', '3': '⬆️',
        '4': '➡️', '5': '⬅️', '6': '➡️',
        '7': '➡️', '8': '⬆️', '9': '⬆️'
    }
    return tabla.get(numero, '❌')

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
        await update.message.reply_text(
            f"✨ ¡Bienvenido {nombre} al Quidditch Emoji Bot! ✨\n\n"
            "Para comenzar, necesitas crear una cuenta.\n\n"
            "Comando: /crear_cuenta\n\n"
            "Serás parte de una de las tres casas mágicas: Galkin ❤️, Darfor 💜 u Olsson 💚"
        )
    else:
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
                        f"✅ ¡GOL! +10 puntos (en práctica es un simulacro)"
                    )
                
                    # Reiniciar práctica después del gol
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
    
    elif context.user_data.get('esperando_casa'):
        casa = update.message.text
        if casa in ["Galkin", "Darfor", "Olsson"]:
            user_id = update.effective_user.id
            nombre = update.effective_user.first_name
            
            conn = sqlite3.connect('quidditch.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usuarios (id_telegram, nombre, casa, cargo, fecha_registro) VALUES (?, ?, ?, ?, ?)",
                (user_id, nombre, casa, "Estudiante", datetime.now())
            )
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                f"✅ ¡Cuenta creada!\n\n"
                f"Nombre: {nombre}\n"
                f"Casa: {casa}\n"
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
        [InlineKeyboardButton("📜 Reglas generales", callback_data="aprender_general"), InlineKeyboardButton("🔴 Cazador", callback_data="aprender_cazador")],
        [InlineKeyboardButton("🟡 Guardián", callback_data="aprender_guardian"), InlineKeyboardButton("🟢 Golpeador", callback_data="aprender_golpeador")],
        [InlineKeyboardButton("🟣 Buscador", callback_data="aprender_buscador"), InlineKeyboardButton("⚡ Práctica rápida", callback_data="aprender_practica")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📚 *CENTRO DE APRENDIZAJE*\n\nElige una opción:", reply_markup=reply_markup, parse_mode="Markdown")

async def boton_aprender(update, context):
    query = update.callback_query
    await query.answer()
    opcion = query.data
    textos = {
        "aprender_general": "📜 *REGLAS GENERALES*\n\nGol = 100 pts | Snitch = 150 pts\nGolpe efectivo = 50 pts",
        "aprender_cazador": "🔴 *CAZADOR*\n\nPases: mínimo 4, máximo 10\nDisparo: [Casa]🏉[Aro]123",
        "aprender_guardian": "🟡 *GUARDIÁN*\n\nDefensa: 5 segundos\nTabla: 1⬅️ 2⬅️ 3⬆️ 4➡️ 5⬅️ 6➡️ 7➡️ 8⬆️ 9⬆️",
        "aprender_golpeador": "🟢 *GOLPEADOR*\n\nGolpe: [Casa]🏏💥123@rival\nDefensa: [Casa]🧹⬅️⬆️➡️🏏❌",
        "aprender_buscador": "🟣 *BUSCADOR*\n\nCaptura snitch: copiar secuencia de flechas",
        "aprender_practica": "⚡ *PRÁCTICA RÁPIDA*\n\nPróximamente"
    }
    texto = textos.get(opcion, "Opción no válida")
    await query.edit_message_text(texto, parse_mode="Markdown")

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
    await query.edit_message_text("🔴 *PRÁCTICA DE CAZADOR*\n\nEscribe 'salir' para terminar.", parse_mode="Markdown")

async def practicar_guardian(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['practica_activa'] = 'guardian'
    await query.edit_message_text("🟡 *PRÁCTICA DE GUARDIÁN*\n\nEscribe 'salir' para terminar.", parse_mode="Markdown")

async def practicar_golpeador(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['practica_activa'] = 'golpeador'
    await query.edit_message_text("🟢 *PRÁCTICA DE GOLPEADOR*\n\nEscribe 'salir' para terminar.", parse_mode="Markdown")

async def practicar_buscador(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['practica_activa'] = 'buscador'
    await query.edit_message_text("🟣 *PRÁCTICA DE BUSCADOR*\n\nEscribe 'salir' para terminar.", parse_mode="Markdown")

async def salir_practica(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['practica_activa'] = None
    await query.edit_message_text("✅ Has salido del modo práctica.")

async def jugar(update, context):
    await update.message.reply_text("🏆 *MODO JUGAR*\n\nPróximamente.", parse_mode="Markdown")

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
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensajes))
    
    print("🐲 Bot de Quidditch iniciado...")
    
    threading.Thread(target=run_web).start()
    app.run_polling()

if __name__ == "__main__":
    main()