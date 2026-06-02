import discord
import requests
from discord.ext import commands
from discord import ui
import smtplib
from email.mime.text import MIMEText
import random
import os
from dotenv import load_dotenv
from aiohttp import web

# 1. Configuración de credenciales y entorno
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# Guardamos los IDs importantes
GUILD_ID = int(os.getenv('GUILD_ID', 0)) 
ROLE_VERIFICADO_ID = int(os.getenv('ROLE_VERIFICADO_ID', 0))

# Diccionario temporal en memoria: { ID_Discord: {"correo": "...", "codigo": "..."} }
datos_verificacion = {}

# --- FUNCIÓN: Envío de Correo (Ejecutada en segundo plano con Timeout e IPv4 Forzado) ---
def enviar_correo_verificacion(correo_alumno, codigo_seguridad):
    try:
        print(f"🌐 [LOG] Enviando señal a Make para: {correo_alumno}...")
        
        # Pega aquí la URL de tu webhook de Make
        webhook_url = "https://hook.eu1.make.com/c1sfphwwhlv3wov2546nmihk64bgl2gk" 
        
        datos = {
            "correo": correo_alumno,
            "codigo": codigo_seguridad
        }
        
        # Enviamos la solicitud HTTP (Puerto 443), Render jamás bloqueará esto
        respuesta = requests.post(webhook_url, json=datos, timeout=10.0)
        
        if respuesta.status_code == 200:
            print("✨ [LOG] ¡Make recibió la orden y envió el correo con éxito!")
            return True
        else:
            print(f"⚠️ [LOG] Make respondió con error: {respuesta.status_code}")
            return False

    except Exception as e:
        print(f"❌ [LOG] Error al contactar el webhook: {e}")
        return False

# --- INTERFAZ: Formulario para ingresar el Código recibido ---
class ModalCodigo(ui.Modal, title="Paso 2: Introduce tu Código"):
    input_codigo = ui.TextInput(label="Código de 6 dígitos", placeholder="Escribe el código que te llegó al correo", min_length=6, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        codigo_ingresado = self.input_codigo.value.strip()

        # Validamos si el usuario tiene un código pendiente y coincide
        if user_id in datos_verificacion and datos_verificacion[user_id]["codigo"] == codigo_ingresado:
            guild = interaction.guild
            rol = guild.get_role(ROLE_VERIFICADO_ID)
            
            if rol:
                await interaction.user.add_roles(rol) # Asignamos el rol oficial
                await interaction.response.send_message(f"🎉 ¡Felicidades, {interaction.user.mention}! Has sido verificado con éxito. El campus se ha desbloqueado para ti.", ephemeral=True)
                if user_id in datos_verificacion:
                    del datos_verificacion[user_id] # Limpiamos memoria de manera segura
            else:
                await interaction.response.send_message("❌ Error de configuración: El rol de verificación no existe en este servidor.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Código incorrecto. Por favor, vuelve a intentarlo.", ephemeral=True)

# --- INTERFAZ: Formulario para ingresar el Correo del Tec ---
class ModalCorreo(ui.Modal, title="Paso 2: Verificación Institucional"):
    correo = ui.TextInput(
        label="Correo del Tec", 
        placeholder="A0XXXXXXX@tec.mx", 
        min_length=12
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Traemos el correo, le quitamos espacios y lo pasamos a minúsculas
        correo = self.correo.value.strip().lower()
        
        # 🔒 CANDADO DE SEGURIDAD: Validamos que termine con dominio institucional
        if not (correo.endswith('@tec.mx') or correo.endswith('@itesm.mx')):
            await interaction.response.send_message(
                "❌ **Acceso denegado.** Debes ingresar un correo institucional válido del Tec (que termine en `@tec.mx` o `@itesm.mx`).", 
                ephemeral=True
            )
            return # Detenemos la ejecución aquí mismo para que no mande nada a Make

        # 2. Si pasa el candado, le decimos a Discord que espere el proceso asíncrono
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        # 3. Generamos el código numérico y lo guardamos inmediatamente en memoria
        codigo = str(random.randint(100000, 999999))
        datos_verificacion[user_id] = {"correo": correo, "codigo": codigo}

        # 4. Lanzamos el envío del correo en un hilo secundario sin congelar el bot
        import asyncio
        print(f"🧵 [LOG] Lanzando envío de correo en hilo separado para {correo}...")
        exito = await asyncio.to_thread(enviar_correo_verificacion, correo, codigo)

        # 5. Evaluamos el resultado del envío
        if exito:
            view = ui.View(timeout=600.0) # 10 minutos de margen para los alumnos
            btn_codigo = ui.Button(label="Ingresar Código", style=discord.ButtonStyle.green)
            
            async def click_codigo(inter):
                await inter.response.send_modal(ModalCodigo())
            
            btn_codigo.callback = click_codigo
            view.add_item(btn_codigo)

            await interaction.followup.send(
                f"📧 Te hemos enviado un código a **{correo}**. Revisa tu bandeja de entrada (y carpeta de No deseados/Spam) y haz clic abajo para ingresarlo.", 
                view=view, 
                ephemeral=True
            )
        else:
            if user_id in datos_verificacion:
                del datos_verificacion[user_id]
            await interaction.followup.send(
                "❌ Hubo un problema al enviar el correo. Por favor contacta al staff del servidor.", 
                ephemeral=True
            )

# --- INTERFAZ: El Botón Estático del Canal de Bienvenida ---
class VistaBotonInicio(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Botón persistente

    @ui.button(label="Iniciar Verificación Borrego 🐏", style=discord.ButtonStyle.blurple, custom_id="btn_inicio_verificacion")
    async def boton_inicio(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModalCorreo())

# --- Configuración Base e Inicialización del Bot ---
class VerificacionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Encendemos el servidor web integrado al iniciar el bot
        self.loop.create_task(iniciar_servidor_web())

    async def on_ready(self):
        print(f'=============================================')
        print(f'✅ ¡Bot encendido y conectado con éxito!')
        print(f'🤖 Nombre del bot: {self.user}')
        print(f'=============================================')
        self.add_view(VistaBotonInicio())

# Creamos la instancia única global del bot
bot = VerificacionBot()

# Comando administrativo para desplegar el botón en el canal deseado
@bot.command()
@commands.has_permissions(administrator=True)
async def desplegar_boton(ctx):
    embed = discord.Embed(
        title="🔒 Verificación Obligatoria de Alumnos",
        description="¡Bienvenido al servidor de la Comunidad Estudiantil del Tec!\n\nPara desbloquear el acceso a tu escuela y a los chats generales, presiona el botón de abajo e ingresa tu correo institucional.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=VistaBotonInicio())
    await ctx.message.delete()

# --- INFRAESTRUCTURA: Servidor Web de Respaldo para Render (Keep-Alive) ---
async def home(request):
    return web.Response(text="¡Bot de Verificación en línea 24/7!")

async def iniciar_servidor_web():
    app = web.Application()
    app.router.add_get('/', home)
    runner = web.AppRunner(app)
    await runner.setup()
    puerto = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", puerto)
    await site.start()
    print(f"🌐 Servidor web de respaldo encendido en el puerto {puerto}")

# Entrada del programa principal
if __name__ == '__main__':
    bot.run(TOKEN)