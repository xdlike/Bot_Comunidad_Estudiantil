import discord
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
        # Redacción diseñada para mitigar filtros antispam
        cuerpo = f"Qué onda,\n\nTe paso el número de registro para lo de la Comunidad Estudiantil:\n\n{codigo_seguridad}\n\nSaludos."
        msg = MIMEText(cuerpo)
        msg['Subject'] = 'Folio de ingreso - Comunidad'
        msg['From'] = EMAIL_SENDER
        msg['To'] = correo_alumno

        print(f"🔌 [LOG] Conectando a Gmail para enviar código a: {correo_alumno}...")
        
        # 🌐 TRUCO CLAVE: Forzamos la resolución de Gmail estrictamente a IPv4 numérico
        import socket
        try:
            gmail_ipv4 = socket.gethostbyname('smtp.gmail.com')
            print(f"🔍 [LOG] IP de Gmail forzada a IPv4: {gmail_ipv4}")
        except Exception as socket_error:
            print(f"⚠️ [LOG] Falló resolución IPv4, usando host por defecto: {socket_error}")
            gmail_ipv4 = 'smtp.gmail.com'
        
        # Conexión usando la IP IPv4 fija para saltar el bloqueo de Render
        with smtplib.SMTP(gmail_ipv4, 587, timeout=10.0) as server:
            # server_hostname evita que falle la validación del certificado SSL al usar una IP
            server.starttls(server_hostname='smtp.gmail.com')
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            
        print("✨ [LOG] ¡Correo enviado con éxito desde el hilo secundario!")
        return True
    except Exception as e:
        print(f"❌ [LOG] Error al enviar correo en el hilo: {e}")
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
        # 1. Le decimos a Discord que espere el proceso asíncrono
        await interaction.response.defer(ephemeral=True)
        
        correo = self.correo.value.strip()
        user_id = interaction.user.id
        
        # 2. Generamos el código numérico y lo guardamos inmediatamente en memoria
        codigo = str(random.randint(100000, 999999))
        datos_verificacion[user_id] = {"correo": correo, "codigo": codigo}

        # 3. Lanzamos el envío del correo en un hilo secundario sin congelar el bot
        import asyncio
        print(f"🧵 [LOG] Lanzando envío de correo en hilo separado para {correo}...")
        exito = await asyncio.to_thread(enviar_correo_verificacion, correo, codigo)

        # 4. Evaluamos el resultado del envío
        if exito:
            # Si el correo sale bien, generamos dinámicamente el botón para meter el token
            view = ui.View()
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
            # Si falló la conexión con Gmail, limpiamos el registro fallido y notificamos
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