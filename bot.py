import discord
from discord.ext import commands, tasks
import socket
import zlib
import struct
import time
import asyncio
import logging
import json
import os
import subprocess
import psutil
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PLAYERS_CHANNEL_ID = int(os.getenv("PLAYERS_CHANNEL_ID")) # Canal pour les joueurs
LOGS_CHANNEL_ID = int(os.getenv("LOGS_CHANNEL_ID"))      # Canal pour les logs
CONTROL_CHANNEL_ID = int(os.getenv("CONTROL_CHANNEL_ID"))   # Canal pour le contrôle serveur

# Configuration RCON
RCON_SERVER = (os.getenv("RCON_HOST"), int(os.getenv("RCON_PORT")))
RCON_PASSWORD = os.getenv("RCON_PASSWORD") 
# Configuration serveur
SERVER_PORT = int(os.getenv("SERVER_PORT") )
SERVER_BAT = os.getenv("SERVER_BAT") 
WORKING_DIR_BAT = os.getenv("WORKING_DIR_BAT") 
PROCESS_NAME = os.getenv("PROCESS_NAME") 

# Configuration logs
BASE_LOG_DIR = Path(os.getenv("BASE_LOG_DIR") )  # Chemin vers vos fichiers de log
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL") )      # Secondes entre les vérifications de log
POSITIONS_FILE = os.getenv("POSITIONS_FILE") 

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RconClient:
    MAGIC = b'BE'
    END = b'\xff'
    
    def __init__(self, server_address: tuple, password: str):
        self.server = server_address
        self.password = password
        self.sock = None
        self.seq = 0
        self.last_keepalive = time.time()
        self.connected = False
    
    def make_packet(self, payload: bytes) -> bytes:
        crc = zlib.crc32(payload) & 0xffffffff
        return self.MAGIC + struct.pack('<I', crc) + self.END + payload
    
    def connect(self) -> bool:
        """Établit la connexion RCON"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(5)
            
            # Tentative de login
            payload = b'\x00' + self.password.encode('ascii')
            self.sock.sendto(self.make_packet(payload), self.server)
            
            data, _ = self.sock.recvfrom(4096)
            payload = data[7:]
            success = payload[1] == 1
            
            if success:
                self.connected = True
                logger.info("Connexion RCON établie")
            else:
                logger.error("Échec de la connexion RCON")
                
            return success
            
        except Exception as e:
            logger.error(f"Erreur lors de la connexion RCON: {e}")
            return False
    
    def getPlayers(self, cmd: str) -> Optional[str]:
        """Envoie une commande RCON"""
        if not self.connected or not self.sock:
            return None
            
        try:
            # if not self.connected
            #     self.connect()
                
            # self.seq = (self.seq + 1) % 256
            # payload = b'\x01' + bytes([self.seq]) + cmd.encode('ascii')
            # self.sock.sendto(self.make_packet(payload), self.server)
            # print("sending command")

            
            # Collecter toutes les réponses
            start_time = time.time()
            timeout = 30.0
            processing = False
            
            while time.time() - start_time < timeout:
                if self.connect and not processing: 
                    self.seq = (self.seq + 1) % 256
                    payload = b'\x01' + bytes([self.seq]) + cmd.encode('ascii')
                    self.sock.sendto(self.make_packet(payload), self.server)
                elif not self.connect: 
                    self.connect()
                    
                try:
                    data, _ = self.sock.recvfrom(4096)
                    payload = data[7:]
                    if payload and payload[0] == 2:
                        rseq = payload[1]
                        msg = payload[2:].decode('ascii', errors='ignore')
                        print(f"Server message [{rseq}]:", msg.strip())
                        ack = b'\x02' + bytes([rseq])
                        self.sock.sendto(self.make_packet(ack), self.server)
                        if 'Players on server:' in msg: 
                            lines = msg.strip().split('\n')
                            player_names = []
                            for line in lines[1:]:
                                parts = [p.strip() for p in line.split(';')]
                                if len(parts) >= 3:
                                    player_names.append(parts[2])
                            return player_names
                        elif 'Processing Command:' in msg:
                                processing = True
                                logger.info("Processing command response...")
                except socket.timeout:
                    continue
                    
            return None
                
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de commande: {e}")
            self.connect()
            return None
    
    def keep_alive(self):
        """Maintient la connexion active"""
        if not self.connected or not self.sock:
            return
            
        try:
            self.seq = (self.seq + 1) % 256
            payload = b'\x01' + bytes([self.seq])
            self.sock.sendto(self.make_packet(payload), self.server)
            self.last_keepalive = time.time()
            
        except Exception as e:
            logger.error(f"Erreur keep-alive: {e}")
            self.connected = False
    
    def disconnect(self):
        """Ferme la connexion"""
        if self.sock:
            self.sock.close()
            self.sock = None
        self.connected = False
        logger.info("Connexion RCON fermée")

class ServerControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    def is_port_in_use(self, port):
        try:
            for conn in psutil.net_connections(kind='udp'):
                if conn.laddr.port == port:
                    return True
            return False
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False

    def stop_arma_server(self):
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and PROCESS_NAME.lower() in proc.info['name'].lower():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    return True
                except psutil.TimeoutExpired:
                    proc.kill()
                    return True
        return False

    def start_arma_server(self):
        process = subprocess.Popen(
            WORKING_DIR_BAT+SERVER_BAT, 
            shell=True, 
            cwd=WORKING_DIR_BAT,  # This sets the working directory
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

    @discord.ui.button(label="🟢 Start Server", style=discord.ButtonStyle.green)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Seuls les administrateurs peuvent démarrer le serveur.", ephemeral=True)
            return
        if self.is_port_in_use(SERVER_PORT):
            await interaction.response.send_message("⚠️ Server is already running.", ephemeral=True)
        else:
            self.start_arma_server()
            await interaction.response.send_message("✅ Starting the server...", ephemeral=True)

    @discord.ui.button(label="🔴 Stop Server", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Seuls les administrateurs peuvent arrêté le serveur.", ephemeral=True)
            return
        if not self.is_port_in_use(SERVER_PORT):
            await interaction.response.send_message("⚠️ Server is not running.", ephemeral=True)
        else:
            stopped = self.stop_arma_server()
            msg = "✅ Server stopped." if stopped else "❌ Could not stop the server."
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="♻️ Restart Server", style=discord.ButtonStyle.blurple)
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Seuls les administrateurs peuvent redémarrer le serveur.", ephemeral=True)
            return
        restarting = False
        if self.is_port_in_use(SERVER_PORT):
            restarting = self.stop_arma_server()
            await asyncio.sleep(3)
        self.start_arma_server()
        msg = "♻️ Server restarted." if restarting else "✅ Server started."
        await interaction.response.send_message(msg, ephemeral=True)

class UnifiedArmaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        # RCON
        self.rcon = RconClient(RCON_SERVER, RCON_PASSWORD)
        self.players_channel = None
        self.players_message = None
        
        # Logs
        self.logs_channel = None
        self.last_positions = self.load_positions()
        
        # Server Control
        self.control_channel = None
        
    def load_positions(self):
        """Charge les positions des fichiers de log"""
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load positions: {e}")
        return {}

    def save_positions(self):
        """Sauvegarde les positions des fichiers de log"""
        try:
            with open(POSITIONS_FILE, "w") as f:
                json.dump(self.last_positions, f)
        except Exception as e:
            logger.error(f"Failed to save positions: {e}")

    def get_latest_log_folder(self):
        """Obtient le dossier de logs le plus récent"""
        if not BASE_LOG_DIR.exists():
            return None
            
        folders = [
            f for f in BASE_LOG_DIR.iterdir()
            if f.is_dir() and f.name.startswith("logs_")
        ]
        return max(folders, key=os.path.getmtime, default=None)
        
    async def setup_hook(self):
        """Configuration initiale du bot"""
        self.update_players.start()
        self.keepalive_task.start()
        self.monitor_logs_task.start()
        
    async def on_ready(self):
        """Appelé quand le bot est connecté"""
        logger.info(f'{self.user} est connecté à Discord!')
        
        # Initialiser les canaux
        self.players_channel = self.get_channel(PLAYERS_CHANNEL_ID)
        self.logs_channel = self.get_channel(LOGS_CHANNEL_ID)
        self.control_channel = self.get_channel(CONTROL_CHANNEL_ID)
        
        # Vérifier les canaux
        if not self.players_channel:
            logger.error(f"Canal joueurs {PLAYERS_CHANNEL_ID} introuvable")
        if not self.logs_channel:
            logger.error(f"Canal logs {LOGS_CHANNEL_ID} introuvable")
        if not self.control_channel:
            logger.error(f"Canal contrôle {CONTROL_CHANNEL_ID} introuvable")
            
        # Connexion RCON
        if not self.rcon.connect():
            logger.error("Impossible de se connecter au serveur RCON")
        else:
            logger.info("Bot prêt et connecté au serveur RCON")
            
        # Envoyer le panneau de contrôle
        if self.control_channel:
            await self.control_channel.send("🎮 Arma Server Control Panel", view=ServerControlView(self))
    
    @tasks.loop(seconds=30)
    async def update_players(self):
        """Met à jour la liste des joueurs toutes les 30 secondes"""
        if not self.players_channel or not self.rcon.connected:
            return

        try:
            response = self.rcon.getPlayers("players")
            if response and len(response) > 0:                
                player_list = '\n'.join([f"• {player}" for player in response])
                embed = discord.Embed(
                    title="🪖 Effectif sur le terrain",
                    description=f"**{len(response)} soldat(s) en service:**\n\n{player_list}",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url="https://thumbs.dreamstime.com/b/soldat-avec-le-casque-30374636.jpg?w=992")
            else:
                embed = discord.Embed(
                    title="🪖 Effectif sur le terrain",
                    description="Aucun soldat en service",
                    color=0xff0000,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url="https://thumbs.dreamstime.com/b/soldat-avec-le-casque-30374636.jpg?w=992")

            # Envoyer ou éditer le message unique
            if self.players_message:
                try:
                    await self.players_message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except discord.NotFound:
                    self.players_message = await self.players_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            else:
                self.players_message = await self.players_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des joueurs: {e}")
    
    @tasks.loop(seconds=30)
    async def keepalive_task(self):
        """Maintient la connexion RCON active"""
        if self.rcon.connected and time.time() - self.rcon.last_keepalive > 25:
            self.rcon.keep_alive()
            
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def monitor_logs_task(self):
        """Surveille les fichiers de logs"""
        if not self.logs_channel:
            return
            
        try:
            latest_folder = self.get_latest_log_folder()
            if not latest_folder:
                return

            for log_file in latest_folder.glob("*.log"):
                log_file_str = str(log_file.resolve())
                last_pos = self.last_positions.get(log_file_str, 0)

                with log_file.open("rb") as f:
                    f.seek(last_pos)
                    raw = f.read()
                    decoded = raw.decode("utf-8", errors="replace")
                    self.last_positions[log_file_str] = f.tell()

                for line in decoded.splitlines():
                    if not line.strip():
                        continue
                    prefix = "❌" if log_file.name == "error.log" else "📄"
                    try:
                        await self.logs_channel.send(f"{prefix} **{log_file.name}**: {line.strip()}")
                    except Exception as e:
                        logger.error(f"Erreur envoi log: {e}")

            self.save_positions()

        except Exception as e:
            logger.error(f"Erreur surveillance logs: {e}")
    
    @update_players.before_loop
    async def before_update_players(self):
        await self.wait_until_ready()
        await asyncio.sleep(5)
    
    @keepalive_task.before_loop
    async def before_keepalive(self):
        await self.wait_until_ready()
        
    @monitor_logs_task.before_loop
    async def before_monitor_logs(self):
        await self.wait_until_ready()
    
    async def close(self):
        """Nettoyage lors de la fermeture du bot"""
        self.update_players.cancel()
        self.keepalive_task.cancel()
        self.monitor_logs_task.cancel()
        self.rcon.disconnect()
        await super().close()


@commands.command(name='status')
async def server_status(ctx):
    """Commande pour vérifier le statut du serveur"""
    bot = ctx.bot
    rcon_status = "✅ Connexion RCON active" if bot.rcon.connected else "❌ Connexion RCON inactive"
    
    # Vérifier si le serveur est en cours d'exécution
    server_running = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        server_running = s.connect_ex(('localhost', SERVER_PORT)) == 0
    
    server_status = "✅ Serveur en cours d'exécution" if server_running else "❌ Serveur arrêté"
    
    embed = discord.Embed(
        title="🔍 Statut du serveur",
        description=f"{rcon_status}\n{server_status}",
        color=0x00ff00 if bot.rcon.connected and server_running else 0xff0000
    )
    await ctx.send(embed=embed)

@commands.command(name='control')
async def show_control_panel(ctx):
    """Affiche le panneau de contrôle du serveur"""
    await ctx.send("🎮 Arma Server Control Panel", view=ServerControlView(ctx.bot))

if __name__ == "__main__":
    bot = UnifiedArmaBot()
    bot.add_command(server_status)
    bot.add_command(show_control_panel)
    
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Arrêt du bot...")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")