import discord
from discord import app_commands
from discord.ext import commands
import os
import re
import requests
import subprocess
import asyncio
import time


# --- GitHub Integration: Fetch token from env and URL definitions ---
TOKEN = os.getenv("CRUEL_STARS_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://raw.githubusercontent.com/Fir3Fly1995/CowBOYs-SC/main/Mini-bot/Bot/"
REPO_URL = f"https://oauth2:{GITHUB_TOKEN}@github.com/Fir3Fly1995/CowBOYs-SC.git"
MESSAGE_URL = BASE_URL + "message.txt"
ROLES_URL = BASE_URL + "roles.txt"
INSTRUCTIONS_URL = BASE_URL + "instructions.txt"
CHANNELS_URL = BASE_URL + "channels.txt"
DATA_DIR = "/app/data" # Directory inside the container to store files


def fetch_file(url, local_path):
    """
    Downloads a file from a given URL and saves it to a local path.
    """
    try:
        r = requests.get(url)
        r.raise_for_status()
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"Successfully fetched and updated {local_path} from GitHub.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file from {url}: {e}")
    except IOError as e:
        print(f"Error saving file to {local_path}: {e}")


def push_to_github():
    """
    Commits and pushes the updated roles.txt file to the GitHub repository.
    """
    if not GITHUB_TOKEN:
        print("GitHub token not found. Skipping push to GitHub.")
        return

    try:
        # Use subprocess to execute git commands
        # Configure Git with user details for the commit
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@example.com'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'CowboysBot'], check=True)

        # Add the roles.txt file
        subprocess.run(['git', 'add', os.path.join(DATA_DIR, 'roles.txt')], check=True)

        # Commit the changes
        subprocess.run(['git', 'commit', '-m', 'Bot updated roles.txt with message ID'], check=True)

        # Push the changes to the repository using the provided token for authentication
        subprocess.run(['git', 'push', REPO_URL, 'main'], check=True)

        print("Successfully pushed changes to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"Error pushing to GitHub: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Git push: {e}")


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
        self.button_roles = {}
        self.roles_file_path = os.path.join(DATA_DIR, "roles.txt")
        self.instructions_file_path = os.path.join(DATA_DIR, "instructions.txt")
        self.channels_file_path = os.path.join(DATA_DIR, "channels.txt")
        self.message_file_path = os.path.join(DATA_DIR, "message.txt")

    async def setup_hook(self):
        # Sync slash commands on startup
        await self.tree.sync()
        print(f'{self.user} has connected to Discord!')
        # Note: We no longer load reaction roles at startup,
        # but rather when the /setuproles command is called.


    async def on_ready(self):
        """
        Runs when the bot has successfully connected to Discord.
        """
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

        # Send "I am alive" message to specified channels
        try:
            # Ensure the data directory exists
            os.makedirs(DATA_DIR, exist_ok=True)
            fetch_file(CHANNELS_URL, self.channels_file_path)
            with open(self.channels_file_path, "r", encoding="utf-8") as f:
                channel_ids = [line.strip() for line in f if line.strip().isdigit()]
            
            for channel_id_str in channel_ids:
                channel_id = int(channel_id_str)
                channel = self.get_channel(channel_id)
                if channel:
                    await channel.send("Hello! I am alive, please run the `/refreshrole` command to update all message IDs.")
        except Exception as e:
            print(f"Error sending 'I am alive' messages: {e}")

    def load_reaction_roles(self):
        """
        Loads and parses the roles.txt file to populate the reaction_roles dictionary.
        This function is designed to handle multiple message blocks.
        """
        if not os.path.exists(self.roles_file_path):
            print(f"Roles file not found at: {self.roles_file_path}")
            return {}
            
        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split the content into individual blocks
        blocks = re.split(r'Start\.|Skip\.', content, flags=re.IGNORECASE)[1:]
        
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
                # We now need to find the end of the message text, which can be either EMOTE or MK-BTN
                msg_end_emote = block.find("EMOTE_1;", msg_start)
                msg_end_btn = block.find("MK-BTN_1;", msg_start)

                if msg_end_emote != -1 and (msg_end_btn == -1 or msg_end_emote < msg_end_btn):
                    message_text = block[msg_start:msg_end_emote].strip()
                elif msg_end_btn != -1:
                    message_text = block[msg_start:msg_end_btn].strip()
                else:
                    message_text = block[msg_start:].strip()
            
            emotes = {}
            buttons = {}
            
            # Parse emotes and role names
            for i, line in enumerate(lines):
                # This regex now correctly captures both unicode and custom emojis
                emote_match = re.search(r'EMOTE_(\d+);\s*(<.+?|.+?)\s*\"(.+?)\"', line)
                if emote_match:
                    # Stripping the whitespace from the captured emoji string
                    emote = emote_match.group(2).strip()
                    label = emote_match.group(3).strip()
                    emote_number = emote_match.group(1)
                    
                    is_toggle = False
                    # Check for 'Toggle-Role' on the next line
                    if i + 1 < len(lines) and lines[i+1].strip().lower() == "toggle-role":
                        is_toggle = True
                    
                    # Ensure the emote number matches the give role number
                    give_role_match = re.search(f'Give_Role_{emote_number};\s*\"(.+?)\"', block)
                    if give_role_match:
                        role_name = give_role_match.group(1).strip()
                        emotes[emote] = {"label": label, "role_name": role_name, "is_toggle": is_toggle}
                        
            # Parse buttons and role names
            for i, line in enumerate(lines):
                button_match = re.search(r'MK-BTN_(\d+);\s*Colour=(\S+);\s*Emoji=(\S+);\s*Text=\"(.+?)\"', line)
                if button_match:
                    button_number = button_match.group(1)
                    color = button_match.group(2)
                    emoji = button_match.group(3)
                    text = button_match.group(4)
                    
                    is_toggle = False
                    if i + 1 < len(lines) and lines[i+1].strip().lower() == "toggle-role":
                        is_toggle = True
                    
                    give_role_matches = re.findall(f'Give_Role_{button_number};\s*\"(.+?)\"', block)
                    if give_role_matches:
                        role_names = [r.strip() for r in give_role_matches]
                        buttons[button_number] = {
                            "color": color.upper(),
                            "emoji": emoji,
                            "text": text,
                            "role_names": role_names,
                            "is_toggle": is_toggle
                        }

            parsed_data[channel_id] = {
                "message_id": message_id,
                "replace_msg": replace_msg,
                "message_text": message_text,
                "emotes": emotes,
                "buttons": buttons
            }
        
        # Populate the bot's reaction_roles dictionary with the new structure
        self.reaction_roles = {}
        self.button_roles = {}
        for channel_id, data in parsed_data.items():
            if data['message_id']:
                self.reaction_roles[str(data['message_id'])] = data['emotes']
                self.button_roles[str(data['message_id'])] = data['buttons']
        return parsed_data


    def _mark_block_as_skipped(self, channel_id, message_id):
        """
        Rewrites the roles.txt file, replacing 'Start.' with 'Skip.'
        and adding the message ID below the channel ID.
        """
        if not os.path.exists(self.roles_file_path):
            return

        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Regex to find the entire block that starts with 'Start.' and contains the specific CH-ID
        block_pattern = re.compile(f'(Start\\.\\s*\\n\\s*CH-ID<#(\d+)>.*?\\n\\s*End\\.)', re.DOTALL | re.IGNORECASE)
        match = block_pattern.search(content)

        if not match:
            return

        full_block = match.group(0)
        
        # 1. Replace 'Start.' with 'Skip.'
        new_block = full_block.replace("Start.", "Skip.", 1)
        
        # 2. Add the MSG-ID right after the CH-ID line.
        # First, remove any existing MSG-ID to prevent duplicates.
        new_block = re.sub(r'MSG-ID:\d+\s*\n', '', new_block, flags=re.IGNORECASE)
        
        ch_id_line = f"CH-ID<#{channel_id}>"
        # Now, insert the new MSG-ID line right after the CH-ID line.
        new_block = re.sub(
            f'({re.escape(ch_id_line)})',
            f'\\1\nMSG-ID:{message_id}',
            new_block,
            1,
            flags=re.IGNORECASE
        )
        
        # Replace the original block in the content with the new, modified block.
        final_content = content.replace(full_block, new_block, 1)

        with open(self.roles_file_path, "w", encoding="utf-8") as f:
            f.write(final_content)
            
        # PUSH TO GITHUB MOVED TO END OF _PROCESS_ROLES_MESSAGES


    def _unmark_all_blocks(self):
        """
        Rewrites the roles.txt file, replacing 'Skip.' with 'Start.',
        and removing all MSG-ID and Replace_MSG lines.
        """
        if not os.path.exists(self.roles_file_path):
            print("roles.txt not found. Cannot unmark blocks.")
            return

        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Replace all 'Skip.' with 'Start.'
        content = re.sub(r'Skip\.', 'Start.', content, flags=re.IGNORECASE)

        # Remove all MSG-ID lines
        content = re.sub(r'MSG-ID:\d+\s*\n', '', content, flags=re.IGNORECASE)

        # Remove all Replace_MSG lines
        content = re.sub(r'Replace_MSG\s*\n', '', content, flags=re.IGNORECASE)

        with open(self.roles_file_path, "w", encoding="utf-8") as f:
            f.write(content)


def _get_parsed_data(roles_file_path):
    """
    Parses the roles.txt file and returns the parsed data.
    """
    parsed_data = {}
    if not os.path.exists(roles_file_path):
        return parsed_data
    
    with open(roles_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = re.split(r'Start\.|Skip\.', content, flags=re.IGNORECASE)[1:]
    
    for block in blocks:
        lines = block.strip().split('\n')
        
        channel_id_match = re.search(r'CH-ID<#(\d+)>', block)
        if not channel_id_match:
            continue
        channel_id = int(channel_id_match.group(1))

        message_id_match = re.search(r'MSG-ID:(\d+)', block)
        message_id = int(message_id_match.group(1)) if message_id_match else None
        
        parsed_data[channel_id] = {"message_id": message_id}
        
    return parsed_data


async def _process_roles_messages(interaction: discord.Interaction, is_silent: bool):
    """
    Core logic for creating/updating roles messages.
    """
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest roles.txt from GitHub before processing it
    file_path = os.path.join(DATA_DIR, "roles.txt")
    fetch_file(ROLES_URL, file_path)
    
    parsed_data = bot.load_reaction_roles()
    if not parsed_data:
        await interaction.followup.send("Could not parse roles.txt or file is empty.", ephemeral=is_silent)
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
                # This is the key fix. If the message is not found, we should treat it as a new message.
                print(f"Message with ID {config['message_id']} not found. Will create a new one.")
                config["message_id"] = None
                
            except Exception as e:
                print(f"Error fetching message: {e}")
                continue
            
            # Case 1.1: Replace existing message content
            if config["message_id"] and config["replace_msg"] and config["message_text"]:
                await message_to_edit.edit(content=config["message_text"])

        # Case 2: Create a new message
        view = discord.ui.View(timeout=None)
        
        if config["buttons"]:
            for _, btn_data in config["buttons"].items():
                button = RoleButton(
                    color=btn_data['color'],
                    emoji=btn_data['emoji'],
                    text=btn_data['text'],
                    role_names=btn_data['role_names'],
                    is_toggle=btn_data['is_toggle'],
                    bot=bot
                )
                view.add_item(button)
        
        if not config["message_id"]:
            if config["message_text"]:
                reaction_message = await channel.send(
                    content=config["message_text"],
                    view=view
                )
                config["message_id"] = reaction_message.id
                
                # Now we need to update the REACTION_ROLES and button_roles dictionaries with the new message ID
                bot.reaction_roles[str(reaction_message.id)] = config['emotes']
                bot.button_roles[str(reaction_message.id)] = config['buttons']
                print(f"New message created with ID: {reaction_message.id}")
            
        else: # Add view to existing message
            if config["buttons"]:
                await message_to_edit.edit(view=view)
        
        # Add reactions to the message
        message_to_react = message_to_edit if message_to_edit else await channel.fetch_message(config["message_id"])
        if message_to_react:
            for emote in config["emotes"]:
                try:
                    await message_to_react.add_reaction(emote)
                except discord.HTTPException as e:
                    print(f"Error adding reaction {emote}: {e}")
                    print("This is likely due to an invalid emoji format in your roles.txt file.")
                    print("Please ensure you are using a raw unicode emoji or the full custom emoji format (<:name:id>).")
                    
        # Mark the block as skipped so it doesn't run again on the next /setuproles
        bot._mark_block_as_skipped(channel_id, config["message_id"])

    push_to_github() # This is the crucial fix!

    await interaction.followup.send("Roles messages have been processed.", ephemeral=is_silent)


bot = RulesBot()

class RoleButton(discord.ui.Button):
    COLOR_MAP = {
        "green": discord.ButtonStyle.success,
        "red": discord.ButtonStyle.danger,
        "blue": discord.ButtonStyle.primary,
        "blurple": discord.ButtonStyle.primary,
        "grey": discord.ButtonStyle.secondary,
        "gray": discord.ButtonStyle.secondary,
    }

    def __init__(self, color, emoji, text, role_names, is_toggle, bot):
        style = self.COLOR_MAP.get(color.lower(), discord.ButtonStyle.secondary)
        super().__init__(style=style, emoji=emoji, label=text)
        self.role_names = role_names
        self.is_toggle = is_toggle
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user

        roles = [discord.utils.get(guild.roles, name=role_name) for role_name in self.role_names]
        roles = [role for role in roles if role is not None]

        if not roles:
            await interaction.followup.send("One or more roles not found. Please contact an admin.", ephemeral=True)
            return

        if self.is_toggle:
            # Toggle all roles
            for role in roles:
                if role in member.roles:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)
            await interaction.followup.send(
                f"Roles updated: {', '.join([role.name for role in roles])}", ephemeral=True
            )
        else:
            # Add all roles if not already present
            added = []
            for role in roles:
                if role not in member.roles:
                    await member.add_roles(role)
                    added.append(role.name)
            if added:
                await interaction.followup.send(
                    f"You have been given the roles: {', '.join(added)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "You already have all the roles.", ephemeral=True
                )


@bot.tree.command(name="message", description="This will post a pre-defined message")
async def message(interaction: discord.Interaction):
    await interaction.response.send_message("Fetching latest message from GitHub...", ephemeral=False)
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest message.txt from GitHub before reading it
    file_path = os.path.join(DATA_DIR, "message.txt")
    fetch_file(MESSAGE_URL, file_path)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.channel.send(f.read())
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=False)


@bot.tree.command(name="msgsilent", description="Posts a pre-defined message silently.")
async def msgsilent(interaction: discord.Interaction):
    await interaction.response.send_message("Posting message silently...", ephemeral=True)
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest message.txt from GitHub before reading it
    file_path = os.path.join(DATA_DIR, "message.txt")
    fetch_file(MESSAGE_URL, file_path)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.channel.send(f.read())
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


@bot.tree.command(name="rolemsg", description="This is to push the stored roles messages to the defined channels.")
@app_commands.default_permissions(manage_roles=True)
async def rolemsg(interaction: discord.Interaction):
    """
    Parses roles.txt and performs the configured actions.
    """
    await interaction.response.send_message("Fetching latest roles file from GitHub...", ephemeral=False)
    await _process_roles_messages(interaction, False)


@bot.tree.command(name="rolesilent", description="This is to push the stored roles messages silently.")
@app_commands.default_permissions(manage_roles=True)
async def rolesilent(interaction: discord.Interaction):
    """
    Parses roles.txt and performs the configured actions silently.
    """
    await interaction.response.send_message("Fetching latest roles file from GitHub and processing silently...", ephemeral=True)
    await _process_roles_messages(interaction, True)


@bot.tree.command(name="refreshrole", description="Refreshes all roles messages in all channels.")
@app_commands.default_permissions(manage_roles=True)
async def refreshrole(interaction: discord.Interaction):
    """
    Refreshes all roles messages in all channels following a 5-step process.
    """
    await interaction.response.send_message("Starting refresh process...", ephemeral=True)
    
    try:
        # Step 1: Fetch roles.txt file from GitHub.
        roles_file_path = os.path.join(DATA_DIR, "roles.txt")
        fetch_file(ROLES_URL, roles_file_path)
        print("Step 1 complete: roles.txt fetched from GitHub.")
        await asyncio.sleep(1)
        
        # Step 2: Delete old messages based on IDs from the fetched file.
        parsed_data = _get_parsed_data(roles_file_path)
        for channel_id, config in parsed_data.items():
            if config["message_id"]:
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(config["message_id"])
                        await message.delete()
                        print(f"Deleted old message with ID: {config['message_id']} from channel {channel.name}")
                    except discord.NotFound:
                        print(f"Message with ID {config['message_id']} not found. Skipping deletion.")
                    except Exception as e:
                        print(f"Error deleting message: {e}")
        print("Step 2 complete: Old messages deleted.")
        await asyncio.sleep(1)
        
        # Step 3: Clean up the local roles.txt file.
        bot._unmark_all_blocks()
        print("Step 3 complete: Local roles.txt cleaned.")
        await asyncio.sleep(1)
        
        # Step 4: Run the rolesilent command logic to create new messages.
        await _process_roles_messages(interaction, True)
        print("Step 4 complete: New messages created.")
        
        # Step 5: The _process_roles_messages function handles the final push to GitHub.
        print("Step 5 is part of the previous step. Process complete.")
        
    except Exception as e:
        await interaction.followup.send(f"An error occurred during the refresh process: {e}", ephemeral=True)
        print(f"An error occurred during the refresh process: {e}")


@bot.tree.command(name="assistme", description="This will silently give you guidance on how to write the roles.txt file.")
async def assistme(interaction: discord.Interaction):
    await interaction.response.send_message("Fetching instructions...", ephemeral=True)
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the instructions.txt from GitHub before reading it
    file_path = os.path.join(DATA_DIR, "instructions.txt")
    fetch_file(INSTRUCTIONS_URL, file_path)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.followup.send(f.read(), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


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

        # Explicitly fetch the member from the API to ensure the object is up-to-date
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            print(f"Member with ID {payload.user_id} not found.")
            return

        if member.bot:
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

        # Explicitly fetch the member from the API to ensure the object is up-to-date
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            print(f"Member with ID {payload.user_id} not found.")
            return

        if member.bot:
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
