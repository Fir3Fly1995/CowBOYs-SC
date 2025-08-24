import discord
from discord import app_commands
from discord.ext import commands


# Read the bot token from a file
with open(r"D:\Github\Tokens\CowBOYs_Token.txt", "r", encoding="utf-8") as token_file:
    TOKEN = token_file.read().strip()

intents = discord.Intents.default()  # guilds is True by default

class RulesBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands on startup
        await self.tree.sync()

bot = RulesBot()





@bot.tree.command(name="message", description="Post contents of Message.txt from absolute path.")
async def message(interaction: discord.Interaction):
    await interaction.response.send_message("Reading message from file...", ephemeral=True)
    file_path = r"D:\GitHub\CowBOYs-SC\Mini-bot\Bot\Message.txt"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.channel.send(f.read())
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)

if __name__ == "__main__":
    bot.run(TOKEN)
