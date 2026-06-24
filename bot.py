import asyncio
import os
import logging
import subprocess
from datetime import datetime

import discord
from discord.ext import tasks

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── Config via variables d'environnement ────────────────────
TOKEN      = os.environ["DISCORD_TOKEN"]
GUILD_ID   = int(os.environ["GUILD_ID"])
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
STREAM_URL = os.environ.get("STREAM_URL", "https://icecast.skyrock.net/s/natio_aac_128k")

# ─── Bot ─────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.voice_states = True
client = discord.Client(intents=intents)

voice_client = None
ffmpeg_process = None


def get_ffmpeg_source():
    """Crée une source audio FFmpeg pour le stream radio."""
    return discord.FFmpegPCMAudio(
        STREAM_URL,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options="-vn"
    )


async def join_and_play():
    """Rejoint le salon vocal et lance le stream."""
    global voice_client

    guild = client.get_guild(GUILD_ID)
    if not guild:
        log.error("❌ Serveur introuvable. Vérifie GUILD_ID.")
        return

    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        log.error("❌ Salon vocal introuvable. Vérifie CHANNEL_ID.")
        return

    log.info(f"🔊 Connexion au salon : #{channel.name}")

    try:
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect(force=True)

        voice_client = await channel.connect()
        log.info("✅ Connecté au salon vocal !")
        start_stream()

    except Exception as e:
        log.error(f"❌ Erreur lors de la connexion : {e}")
        await asyncio.sleep(10)
        await join_and_play()


def start_stream():
    """Lance la diffusion du flux radio."""
    global voice_client

    if not voice_client or not voice_client.is_connected():
        log.warning("⚠️  Pas connecté au salon vocal.")
        return

    if voice_client.is_playing():
        voice_client.stop()

    source = discord.PCMVolumeTransformer(get_ffmpeg_source(), volume=1.0)

    def after_play(error):
        if error:
            log.error(f"❌ Erreur stream : {error}")
        log.info("🔄 Stream terminé. Redémarrage dans 3 s…")
        asyncio.run_coroutine_threadsafe(restart_stream(), client.loop)

    voice_client.play(source, after=after_play)
    log.info("▶️  Radio en cours de diffusion !")


async def restart_stream():
    """Redémarre le stream après une coupure."""
    await asyncio.sleep(3)
    if voice_client and voice_client.is_connected():
        start_stream()
    else:
        log.info("🔄 Reconnexion au salon vocal…")
        await join_and_play()


@tasks.loop(minutes=1)
async def watchdog():
    """Vérifie toutes les minutes que le bot diffuse bien."""
    global voice_client

    if not voice_client or not voice_client.is_connected():
        log.warning("🐕 Watchdog : bot déconnecté, reconnexion…")
        await join_and_play()
    elif not voice_client.is_playing():
        log.warning("🐕 Watchdog : stream arrêté, redémarrage…")
        start_stream()


@client.event
async def on_ready():
    log.info(f"🤖 Bot connecté en tant que {client.user}")
    log.info(f"📻 Stream URL : {STREAM_URL}")
    await join_and_play()
    watchdog.start()


@client.event
async def on_voice_state_update(member, before, after):
    """Reconnecte si le bot est expulsé du salon."""
    if member.id != client.user.id:
        return
    if before.channel and before.channel.id == CHANNEL_ID and (not after.channel or after.channel.id != CHANNEL_ID):
        log.info("👢 Bot expulsé du salon. Reconnexion dans 5 s…")
        await asyncio.sleep(5)
        await join_and_play()


client.run(TOKEN)