import discord
from discord.ext import commands
from discord import ui
import smtplib
from email.mime.text import MIMEText
import random
import os
from dotenv import load_dotenv

# 1. Configuración de credenciales
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# Guardamos los IDs importantes (se obtienen activando el modo desarrollador en Discord)
GUILD_ID = int(os.getenv('GUILD_ID', 0)) 
ROLE_VERIFICADO_ID = int(os.getenv('ROLE_VERIFICADO_ID', 0))

# Diccionario temporal: { ID_Discord: {"correo": "...", "codigo": "..."} }
datos_verificacion = {}

def enviar_correo_verificacion(correo_alumno, codigo_seguridad):
    try:
        # Redacción "inofensiva" para engañar al filtro antispam del Tec
        cuerpo = f"Qué onda,\n\nTe paso el número de registro para lo de la Comunidad Estudiantil:\n\n{codigo_seguridad}\n\nSaludos."
        msg = MIMEText(cuerpo)
        msg['Subject'] = 'Folio de ingreso - Comunidad' # Asunto sin palabras de alerta
        msg['From'] = EMAIL_SENDER
        msg['To'] = correo_alumno

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")
        return False

# --- INTERFAZ: Formulario para ingresar el Código recibido ---
class ModalCodigo(ui.Modal, title="Paso 2: Introduce tu Código"):
    input_codigo = ui.TextInput(label="Código de 6 dígitos", placeholder="Escribe el código que te llegó al correo", min_length=6, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        codigo_ingresado = self.input_codigo.value.strip()

        # Validamos si el usuario tiene un código pendiente y si coincide
        if user_id in datos_verificacion and datos_verificacion[user_id]["codigo"] == codigo_ingresado:
            guild = interaction.guild
            rol = guild.get_role(ROLE_VERIFICADO_ID)
            
            if rol:
                await interaction.user.add_roles(rol) # ¡Le damos el rol de Alumno Verificado!
                await interaction.response.send_message(f"🎉 ¡Felicidades, {interaction.user.mention}! Has sido verificado con éxito. El campus se ha desbloqueado para ti.", ephemeral=True)
                del datos_verificacion[user_id] # Limpiamos la memoria
            else:
                await interaction.response.send_message("❌ Error de configuración: El rol de verificación no existe en este servidor.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Código incorrecto. Por favor, vuelve a intentarlo.", ephemeral=True)

# --- INTERFAZ: Formulario para ingresar el Correo del Tec ---
# --- INTERFAZ: Formulario para ingresar el Correo del Tec ---
class ModalCorreo(ui.Modal, title="Paso 2: Verificación Institucional"):
    # REPARACIÓN: Cambiamos 'input_correo' por 'correo'
    correo = ui.TextInput(
        label="Correo del Tec", 
        placeholder="A0XXXXXXX@tec.mx", 
        min_length=12
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Le decimos a Discord que espere
        await interaction.response.defer(ephemeral=True)
        
        correo = self.correo.value
        
        # 2. 🎲 GENERAR CÓDIGO REAL DE 6 DÍGITOS
        import random
        codigo = str(random.randint(100000, 999999)) 

        # 3. Corremos el envío en un hilo separado
        import asyncio
        exito = await asyncio.to_thread(enviar_correo_verificacion, correo, codigo)

        # 4. Respondemos al alumno
        if exito:
            await interaction.followup.send(
                f"✅ Hemos enviado un código de verificación a **{correo}**. Por favor revisa tu bandeja de entrada (y la carpeta de spam).", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Hubo un problema al enviar el correo. Por favor contacta al staff del servidor.", 
                ephemeral=True
            )

        codigo = str(random.randint(100000, 999999))
        datos_verificacion[interaction.user.id] = {"correo": correo, "codigo": codigo}

        # Enviamos el correo real
        exito = enviar_correo_verificacion(correo, codigo)

        if exito:
            # Si el correo sale bien, le mostramos de inmediato el botón para meter el código
            view = ui.View()
            btn_codigo = ui.Button(label="Ingresar Código", style=discord.ButtonStyle.green)
            
            async def click_codigo(inter):
                await inter.response.send_modal(ModalCodigo())
            
            btn_codigo.callback = click_codigo
            view.add_item(btn_codigo)

            await interaction.followup.send("📧 Te hemos enviado un código a tu correo institucional. Revisa tu bandeja de entrada (y carpeta de No deseados) y da clic abajo para ingresarlo.", view=view, ephemeral=True)
        else:
            await interaction.followup.send("❌ Hubo un problema al enviar el correo. Por favor contacta al staff del servidor.", ephemeral=True)

# --- INTERFAZ: El Botón Estático que se quedará en el canal ---
class VistaBotonInicio(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Timeout None para que el botón nunca expire

    @ui.button(label="Iniciar Verificación Borrego 🐏", style=discord.ButtonStyle.blurple, custom_id="btn_inicio_verificacion")
    async def boton_inicio(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModalCorreo())

# --- Configuración del Bot ---
class VerificacionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)

    # 🔗 AGREGAMOS ESTO: El gancho asíncrono oficial para la nube
    async def setup_hook(self):
        self.loop.create_task(iniciar_servidor_web())

    async def on_ready(self):
        print(f'=============================================')
        print(f'✅ ¡Bot encendido y conectado con éxito!')
        print(f'🤖 Nombre del bot: {self.user}')
        print(f'=============================================')
        # Hacemos que el botón sea persistente
        self.add_view(VistaBotonInicio())

bot = VerificacionBot()

# Comando manual para que tú como Admin generes el botón en el canal deseado
@bot.command()
@commands.has_permissions(administrator=True)
async def desplegar_boton(ctx):  # <--- LISTO, CORREGIDO ✅
    embed = discord.Embed(
        title="🔒 Verificación Obligatoria de Alumnos",
        description="¡Bienvenido al servidor de la Comunidad Estudiantil del Tec!\n\nPara desbloquear el acceso a tu escuela y a los chats generales, presiona el botón de abajo e ingresa tu correo institucional.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=VistaBotonInicio())
    await ctx.message.delete() # Borra el comando !desplegar_boton para que se vea limpio

# --- TRUCO PARA LA NUBE: Mini servidor web para mantener vivo el Bot ---
from aiohttp import web

async def home(request):
    return web.Response(text="¡Bot de Verificación en línea 24/7!")

async def iniciar_servidor_web():
    app = web.Application()
    app.router.add_get('/', home)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render nos da un puerto automáticamente en la variable de entorno 'PORT'
    puerto = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", puerto)
    await site.start()
    print(f"🌐 Servidor web de respaldo encendido en el puerto {puerto}")

bot = VerificacionBot()

# ... (aquí en medio se queda tu comando !desplegar_boton)

if __name__ == '__main__':
    bot.run(TOKEN)

if __name__ == '__main__':
    bot.run(TOKEN)