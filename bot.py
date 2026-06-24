import asyncio
import os
import logging

import discord
from discord.ext import tasks, commands

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────
TOKEN      = os.environ["DISCORD_TOKEN"]
GUILD_ID   = int(os.environ["GUILD_ID"])
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
STREAM_URL = os.environ.get("STREAM_URL", "https://icecast.skyrock.net/s/natio_aac_128k")
PREFIX     = "!"

# ─── Bot ─────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

voice_client = None
is_reconnecting = False


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
        asyncio.run_coroutine_threadsafe(restart_stream(), bot.loop)

    voice_client.play(source, after=after_play)
    log.info("▶️  Radio en cours de diffusion !")


async def restart_stream():
    await asyncio.sleep(3)
    if voice_client and voice_client.is_connected():
        start_stream()
    else:
        await join_and_play()


async def join_and_play():
    global voice_client, is_reconnecting

    if is_reconnecting:
        return
    is_reconnecting = True

    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            log.error("❌ Serveur introuvable.")
            return

        channel = guild.get_channel(CHANNEL_ID)
        if not channel:
            log.error("❌ Salon vocal introuvable.")
            return

        if voice_client and voice_client.is_connected():
            if voice_client.channel.id == CHANNEL_ID:
                start_stream()
                return
            await voice_client.disconnect(force=True)
            voice_client = None
            await asyncio.sleep(2)

        log.info(f"🔊 Connexion au salon : #{channel.name}")
        voice_client = await channel.connect()
        log.info("✅ Connecté !")
        start_stream()

    except Exception as e:
        log.error(f"❌ Erreur connexion : {e}")
        voice_client = None
        await asyncio.sleep(10)
        await join_and_play()

    finally:
        is_reconnecting = False


# ─── Commandes ───────────────────────────────────────────────
@bot.command(name="join", aliases=["radio", "play", "start"])
async def cmd_join(ctx):
    await ctx.message.add_reaction("📻")
    await join_and_play()
    await ctx.send("📻 Skyrock est en cours de diffusion !")


@bot.command(name="leave", aliases=["stop", "dc", "quit"])
async def cmd_leave(ctx):
    global voice_client

    if voice_client and voice_client.is_connected():
        watchdog.stop()
        if voice_client.is_playing():
            voice_client.stop()
        await voice_client.disconnect()
        voice_client = None
        await ctx.message.add_reaction("👋")
        await ctx.send("👋 Déconnecté du salon vocal.")
    else:
        await ctx.send("❌ Je ne suis dans aucun salon vocal.")


@bot.command(name="help", aliases=["aide", "h"])
async def cmd_help(ctx):
    embed = discord.Embed(
        title="📻 Skyrock Radio Bot",
        description="Bot qui diffuse Skyrock en salon vocal 24h/24",
        color=0xFF4500
    )
    embed.add_field(
        name="🎵 Musique",
        value=(
            "`!join` / `!radio` / `!play` / `!start`\n→ Rejoint le salon et lance Skyrock\n\n"
            "`!leave` / `!stop` / `!dc` / `!quit`\n→ Quitte le salon vocal"
        ),
        inline=False
    )
    embed.add_field(
        name="❓ Aide",
        value="`!help` / `!aide`\n→ Affiche ce message",
        inline=False
    )
    embed.set_footer(text="🎶 Skyrock • 96.0 FM")
    await ctx.send(embed=embed)


# ─── Watchdog ────────────────────────────────────────────────
@tasks.loop(minutes=2)
async def watchdog():
    if is_reconnecting:
        return
    if not voice_client or not voice_client.is_connected():
        log.warning("🐕 Watchdog : déconnecté, reconnexion…")
        await join_and_play()
    elif not voice_client.is_playing():
        log.warning("🐕 Watchdog : stream arrêté, redémarrage…")
        start_stream()


@bot.event
async def on_ready():
    log.info(f"🤖 Bot connecté : {bot.user}")
    log.info(f"📻 Stream : {STREAM_URL}")
    log.info("💬 Commandes : !join | !leave | !help")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.user.id:
        return
    if is_reconnecting:
        return
    if before.channel and before.channel.id == CHANNEL_ID:
        if not after.channel or after.channel.id != CHANNEL_ID:
            log.info("👢 Bot expulsé. Reconnexion dans 5 s…")
            await asyncio.sleep(5)
            await join_and_play()


bot.run(TOKEN)