import discord
from discord import app_commands
from discord.ext import commands
import os
import re

# To securely handle tokens, consider using environment variables instead of
# hardcoded paths. For this example, we'll keep the file read.
with open(r"D:\Github\Tokens\CowBOYs_Token.txt", "r", encoding="utf-8") as token_file:
    TOKEN = token_file.read().strip()

# We need to enable specific intents for reactions and members
# This tells Discord that your bot needs to listen for these events.
intents = discord.Intents.default()
intents.reactions = True
intents.members = True


class RulesBot(commands.Bot):
    def __init__(self):
        # We need to pass the updated intents to the bot
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}
        self.roles_file_path = r"D:\GitHub\CowBOYs-SC\Mini-bot\Bot\roles.txt"

    async def setup_hook(self):
        # Sync slash commands on startup
        await self.tree.sync()
        print(f'{self.user} has connected to Discord!')
        # Load the reaction role data from the file on startup
        self.load_reaction_roles()


    def load_reaction_roles(self):
        """
        Loads and parses the roles.txt file to populate the reaction_roles dictionary.
        This function is designed to handle multiple message blocks.
        """
        if not os.path.exists(self.roles_file_path):
            print(f"Roles file not found at: {self.roles_file_path}")
            return
            
        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split the content into individual blocks
        blocks = re.split(r'Start\.', content, flags=re.IGNORECASE)[1:]
        
        parsed_data = {}
        for block in blocks:
            lines = block.strip().split('\n')
            
            # Skip blocks that are marked to be skipped
            if lines[0].strip().startswith("Skip."):
                continue

            # Parse channel ID and name
            channel_id_match = re.search(r'CH-ID<#(\d+)>', block)
            if not channel_id_match:
                continue
            channel_id = int(channel_id_match.group(1))

            message_id_match = re.search(r'MSG-ID:(\d+)', block)
            message_id = int(message_id_match.group(1)) if message_id_match else None
            
            replace_msg = "Replace_MSG" in block

            message_text = None
            if "MSG;" in block:
                msg_start = block.find("MSG;") + 4
                msg_end = block.find("EMOTE_1;", msg_start)
                message_text = block[msg_start:msg_end].strip()
            
            emotes = {}
            # Parse emotes and role names
            for i, line in enumerate(lines):
                emote_match = re.search(r'EMOTE_(\d+);\s*(.+?)\s*\"(.+?)\"', line)
                if emote_match:
                    emote = emote_match.group(2).strip()
                    label = emote_match.group(3).strip()
                    
                    is_toggle = False
                    # Check for 'Toggle-Role' on the next line
                    if i + 1 < len(lines) and lines[i+1].strip().lower() == "toggle-role":
                        is_toggle = True
                    
                    give_role_match = re.search(f'Give_Role_{emote_match.group(1)};\s*\"(.+?)\"', block)
                    if give_role_match:
                        role_name = give_role_match.group(1).strip()
                        emotes[emote] = {"label": label, "role_name": role_name, "is_toggle": is_toggle}
            
            parsed_data[channel_id] = {
                "message_id": message_id,
                "replace_msg": replace_msg,
                "message_text": message_text,
                "emotes": emotes
            }
        
        # Populate the bot's reaction_roles dictionary with the new structure
        self.reaction_roles = {}
        for channel_id, data in parsed_data.items():
            if data['message_id']:
                self.reaction_roles[str(data['message_id'])] = data['emotes']
        return parsed_data


    def _mark_block_as_skipped(self, channel_id):
        """
        Rewrites the roles.txt file, adding 'Skip.' to the processed block.
        """
        if not os.path.exists(self.roles_file_path):
            return

        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = re.compile(f'Start\\.\\s*CH-ID<#{channel_id}>', re.DOTALL | re.IGNORECASE)
        match = pattern.search(content)

        if match:
            start_index = match.start()
            new_content = content[:start_index] + "Skip." + content[start_index:]
            with open(self.roles_file_path, "w", encoding="utf-8") as f:
                f.write(new_content)


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


@bot.tree.command(name="setuproles", description="Sends or updates reaction roles message based on roles.txt.")
@app_commands.default_permissions(manage_roles=True)
async def setuproles(interaction: discord.Interaction):
    """
    Parses roles.txt and performs the configured actions.
    """
    await interaction.response.send_message("Processing roles.txt...", ephemeral=True)

    parsed_data = bot.load_reaction_roles()
    if not parsed_data:
        await interaction.followup.send("Could not parse roles.txt or file is empty.", ephemeral=True)
        return

    for channel_id, config in parsed_data.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"Channel with ID {channel_id} not found.")
            continue
        
        message_to_edit = None
        
        # Case 1: Existing message
        if config["message_id"]:
            try:
                message_to_edit = await channel.fetch_message(config["message_id"])
            except discord.NotFound:
                print(f"Message with ID {config['message_id']} not found.")
                continue
            
            # Case 1.1: Replace existing message content
            if config["replace_msg"] and config["message_text"]:
                await message_to_edit.edit(content=config["message_text"])

        # Case 2: Create a new message
        if not config["message_id"] and config["message_text"]:
            reaction_message = await channel.send(content=config["message_text"])
            config["message_id"] = reaction_message.id
            
            # Now we need to update the REACTION_ROLES dictionary with the new message ID
            bot.reaction_roles[str(reaction_message.id)] = config['emotes']
            print(f"New message created with ID: {reaction_message.id}")
        
        # Add reactions to the message
        message_to_react = message_to_edit if message_to_edit else await channel.fetch_message(config["message_id"])
        if message_to_react:
            for emote in config["emotes"]:
                await message_to_react.add_reaction(emote)

        # Mark the block as skipped so it doesn't run again on the next /setuproles
        bot._mark_block_as_skipped(channel_id)

    await interaction.followup.send("Roles messages have been processed.", ephemeral=True)
    

@bot.listen()
async def on_raw_reaction_add(payload):
    """
    This event fires when a user adds a reaction to a message.
    It works for messages in the cache and for those that are not.
    """
    if str(payload.message_id) in bot.reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return

        # Fetch the member object from the guild
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
            
        emoji = str(payload.emoji)
        if emoji in bot.reaction_roles[str(payload.message_id)]:
            role_data = bot.reaction_roles[str(payload.message_id)][emoji]
            role_name = role_data.get("role_name")
            is_toggle = role_data.get("is_toggle", False)
            
            role = discord.utils.get(guild.roles, name=role_name)
            
            if role is not None:
                if is_toggle:
                    if role in member.roles:
                        # User has the role, so remove it
                        await member.remove_roles(role)
                        print(f"Toggled off role {role.name} for {member.display_name}")
                    else:
                        # User does not have the role, so add it
                        await member.add_roles(role)
                        print(f"Toggled on role {role.name} for {member.display_name}")
                else:
                    # Normal reaction role, add the role
                    await member.add_roles(role)
                    print(f"Adding role {role.name} to {member.display_name}")
                    

@bot.listen()
async def on_raw_reaction_remove(payload):
    """
    This event fires when a user removes a reaction from a message.
    It only removes a role if the reaction is NOT a toggle-role.
    """
    if str(payload.message_id) in bot.reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        emoji = str(payload.emoji)
        if emoji in bot.reaction_roles[str(payload.message_id)]:
            role_data = bot.reaction_roles[str(payload.message_id)][emoji]
            is_toggle = role_data.get("is_toggle", False)

            if not is_toggle:
                role_name = role_data.get("role_name")
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role is not None:
                    print(f"Removing role {role.name} from {member.display_name}")
                    await member.remove_roles(role)


if __name__ == "__main__":
    bot.run(TOKEN)
