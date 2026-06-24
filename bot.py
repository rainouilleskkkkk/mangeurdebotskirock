import asyncio
import os
import logging

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


def get_ffmpeg_source():
    return discord.FFmpegPCMAudio(
        STREAM_URL,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options="-vn"
    )


def start_stream():
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
    await asyncio.sleep(3)
    if voice_client and voice_client.is_connected():
        start_stream()
    else:
        log.info("🔄 Reconnexion au salon vocal…")
        await join_and_play()


async def join_and_play():
    global voice_client

    guild = client.get_guild(GUILD_ID)
    if not guild:
        log.error("❌ Serveur introuvable. Vérifie GUILD_ID.")
        return

    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        log.error("❌ Salon vocal introuvable. Vérifie CHANNEL_ID.")
        return

    # Si déjà connecté au bon salon, relance juste le stream
    if voice_client and voice_client.is_connected():
        if voice_client.channel.id == CHANNEL_ID:
            log.info("✅ Déjà connecté, relance du stream…")
            start_stream()
            return
        else:
            await voice_client.disconnect(force=True)
            voice_client = None
            await asyncio.sleep(1)

    log.info(f"🔊 Connexion au salon : #{channel.name}")

    try:
        voice_client = await channel.connect()
        log.info("✅ Connecté au salon vocal !")
        start_stream()

    except Exception as e:
        log.error(f"❌ Erreur lors de la connexion : {e}")
        await asyncio.sleep(10)
        await join_and_play()


@tasks.loop(minutes=1)
async def watchdog():
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
    if member.id != client.user.id:
        return
    if before.channel and before.channel.id == CHANNEL_ID and (not after.channel or after.channel.id != CHANNEL_ID):
        log.info("👢 Bot expulsé du salon. Reconnexion dans 5 s…")
        await asyncio.sleep(5)
        await join_and_play()


# ─── Gestion des erreurs non capturées ───────────────────────
process_on = asyncio.get_event_loop

client.run(TOKEN)