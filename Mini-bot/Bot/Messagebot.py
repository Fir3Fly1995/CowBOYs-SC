import discord
from discord import app_commands
from discord.ext import commands
import os
import re
import requests
import asyncio
import base64
import json
import datetime


# --- Logging and GitHub Integration ---
# Set to True for verbose console output, False to disable.
VERBOSE_LOGGING = True
# Replace with the actual ID of your admin channel.
ADMIN_CHANNEL_ID = 1414600881864835165 
# Replace with the actual ID of your bot output channel.
BOT_OUTPUT_CHANNEL_ID = 1414966305181798450
# Replace with your User ID for direct pings.
TARGET_USER_ID = 123456789012345678

TOKEN = os.getenv("CRUEL_STARS_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://raw.githubusercontent.com/Fir3Fly1995/CowBOYs-SC/main/Mini-bot/Bot/"
REPO_API_URL = "https://api.github.com/repos/Fir3Fly1995/CowBOYs-SC/contents/Mini-bot/Bot/"
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

def get_file_sha(filepath):
    """
    Gets the SHA of a file from the GitHub repository using the GitHub API.
    """
    if not GITHUB_TOKEN:
        print("GitHub token not found. Cannot get file SHA.")
        return None

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    api_url = f"{REPO_API_URL}{os.path.basename(filepath)}"
    
    try:
        r = requests.get(api_url, headers=headers)
        r.raise_for_status()
        return r.json().get("sha")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            if VERBOSE_LOGGING:
                print(f"File {filepath} not found on GitHub. Creating a new one.")
            return None
        print(f"Error getting file SHA from GitHub: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred getting file SHA: {e}")
        return None


def update_github_file(filepath, commit_message):
    """
    Updates a file on the GitHub repository using the GitHub API.
    """
    if not GITHUB_TOKEN:
        print("GitHub token not found. Skipping push to GitHub.")
        return

    sha = get_file_sha(filepath)
    if sha is None:
        if VERBOSE_LOGGING:
            print("Could not get file SHA. Skipping file update.")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "sha": sha
    }

    api_url = f"{REPO_API_URL}{os.path.basename(filepath)}"
    
    try:
        r = requests.put(api_url, headers=headers, data=json.dumps(payload))
        r.raise_for_status()
        print(f"Successfully updated {filepath} on GitHub.")
    except requests.exceptions.RequestException as e:
        print(f"Error updating file on GitHub: {e}")
        if VERBOSE_LOGGING:
            print(f"Response content: {e.response.text}")


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
        # We now add our persistent view back to the bot on setup
        self.add_view(RoleView(self))

    async def on_ready(self):
        """
        Runs when the bot has successfully connected to Discord.
        """
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

        # Send a direct ping to the target user when the bot comes online.
        await _send_startup_message(self)

        # Run the automated refresh task on startup
        try:
            # Ensure the data directory exists
            os.makedirs(DATA_DIR, exist_ok=True)
            await _perform_refresh_task(self)
        except Exception as e:
            print(f"Error running automated refresh: {e}")

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
        
        # This regex is the fix. It now correctly finds blocks starting with either "Start." or "Skip."
        block_pattern = re.compile(f'((Start|Skip)\\.\\s*\\n\\s*CH-ID<#({channel_id})>.*?\\n\\s*End\\.)', re.DOTALL | re.IGNORECASE)
        match = block_pattern.search(content)

        if not match:
            if VERBOSE_LOGGING:
                print(f"Block for channel {channel_id} not found in roles.txt. Cannot mark as skipped.")
            return

        full_block = match.group(0)
        
        # 1. Replace 'Start.' or 'Skip.' with 'Skip.'
        new_block = re.sub(r'^(Start|Skip)\.', 'Skip.', full_block, flags=re.IGNORECASE | re.MULTILINE)
        
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


class RoleButton(discord.ui.Button):
    COLOR_MAP = {
        "green": discord.ButtonStyle.success,
        "red": discord.ButtonStyle.danger,
        "blue": discord.ButtonStyle.primary,
        "blurple": discord.ButtonStyle.primary,
        "grey": discord.ButtonStyle.secondary,
        "gray": discord.ButtonStyle.secondary,
    }

    def __init__(self, color, emoji, text, role_names, is_toggle):
        style = self.COLOR_MAP.get(color.lower(), discord.ButtonStyle.secondary)
        custom_id = f"role_button:{';'.join(role_names)}:{is_toggle}"
        super().__init__(style=style, emoji=emoji, label=text, custom_id=custom_id)
        self.role_names = role_names
        self.is_toggle = is_toggle

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
            for role in roles:
                if role in member.roles:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)
            await interaction.followup.send(
                f"Roles updated: {', '.join([role.name for role in roles])}", ephemeral=True
            )
        else:
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


class RoleView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_dynamic_buttons()

    def add_dynamic_buttons(self):
        """Adds buttons from roles.txt to the view."""
        os.makedirs(DATA_DIR, exist_ok=True)
        fetch_file(ROLES_URL, os.path.join(DATA_DIR, "roles.txt"))
        
        parsed_data = self.bot.load_reaction_roles()
        
        for _, config in parsed_data.items():
            if config["buttons"]:
                for _, btn_data in config["buttons"].items():
                    # The custom ID must be unique per button type and role
                    custom_id = f"{btn_data['color']}:{btn_data['emoji']}:{btn_data['text']}:{';'.join(btn_data['role_names'])}:{btn_data['is_toggle']}"
                    
                    button = discord.ui.Button(
                        style=RoleButton.COLOR_MAP.get(btn_data['color'].lower(), discord.ButtonStyle.secondary),
                        emoji=btn_data['emoji'],
                        label=btn_data['text'],
                        custom_id=custom_id
                    )
                    self.add_item(button)
                    
    @discord.ui.button(custom_id="role_button:callback")
    async def dynamic_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Handle dynamic button callbacks."""
        
        # Custom ID format: "role_button:<color>:<emoji>:<text>:<role_names_list>:<is_toggle>"
        custom_id_parts = button.custom_id.split(':')
        
        # Acknowledge the interaction immediately.
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user

        # Extract data from the custom_id
        role_names_str = custom_id_parts[3]
        is_toggle = custom_id_parts[4].lower() == 'true'
        role_names = role_names_str.split(';')
        
        roles = [discord.utils.get(guild.roles, name=role_name) for role_name in role_names]
        roles = [role for role in roles if role is not None]

        if not roles:
            await interaction.followup.send("One or more roles not found. Please contact an admin.", ephemeral=True)
            return
            
        if is_toggle:
            for role in roles:
                if role in member.roles:
                    await member.remove_roles(role)
                    if VERBOSE_LOGGING:
                        print(f"Toggled off role {role.name} for {member.display_name}")
                else:
                    await member.add_roles(role)
                    if VERBOSE_LOGGING:
                        print(f"Toggled on role {role.name} for {member.display_name}")
            await interaction.followup.send(
                f"Roles updated: {', '.join([role.name for role in roles])}", ephemeral=True
            )
        else:
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

async def _process_roles_messages(interaction: discord.Interaction, is_ephemeral: bool):
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
        if interaction:
            await interaction.followup.send("Could not parse roles.txt or file is empty.", ephemeral=is_ephemeral)
        return

    for channel_id, config in parsed_data.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            if VERBOSE_LOGGING:
                print(f"Channel with ID {channel_id} not found.")
            continue
        
        message_to_update = None
        new_message_id = None
        
        # Case 1: Existing message
        if config["message_id"]:
            try:
                message_to_update = await channel.fetch_message(config["message_id"])
                if VERBOSE_LOGGING:
                    print(f"Found existing message with ID {config['message_id']}. Attempting to update it.")
            except discord.NotFound:
                # If the message is not found, we should create a new one.
                if VERBOSE_LOGGING:
                    print(f"Message with ID {config['message_id']} not found. Will create a new one.")
                config["message_id"] = None
                
            except Exception as e:
                print(f"Error fetching message: {e}")
                continue
        
        # Case 2: Create or update the message
        view = discord.ui.View(timeout=None)
        
        if config["buttons"]:
            for _, btn_data in config["buttons"].items():
                button = RoleButton(
                    color=btn_data['color'],
                    emoji=btn_data['emoji'],
                    text=btn_data['text'],
                    role_names=btn_data['role_names'],
                    is_toggle=btn_data['is_toggle']
                )
                view.add_item(button)
        
        if message_to_update:
            # We found an existing message, so we'll update it.
            await message_to_update.edit(content=config["message_text"], view=view)
            new_message_id = message_to_update.id
            if VERBOSE_LOGGING:
                print(f"Updated existing message with ID: {new_message_id}")
        else:
            # No existing message, so we'll create a new one.
            reaction_message = await channel.send(
                content=config["message_text"],
                view=view
            )
            new_message_id = reaction_message.id
            if VERBOSE_LOGGING:
                print(f"New message created with ID: {new_message_id}")
            
        # Add reactions to the message
        message_to_react = await channel.fetch_message(new_message_id)
        if message_to_react:
            for emote in config["emotes"]:
                try:
                    await message_to_react.add_reaction(emote)
                except discord.HTTPException as e:
                    print(f"Error adding reaction {emote}: {e}")
                    print("This is likely due to an invalid emoji format in your roles.txt file.")
                    print("Please ensure you are using a raw unicode emoji or the full custom emoji format (<:name:id>).")
                    
        # Mark the block as skipped so it's not handled again
        bot._mark_block_as_skipped(channel_id, new_message_id)

    # This is the crucial fix!
    update_github_file(file_path, "Bot updated roles.txt with new message IDs")

    if interaction:
        await interaction.followup.send("Roles messages have been processed.", ephemeral=is_ephemeral)


async def _perform_refresh_task(bot_instance: commands.Bot, interaction: discord.Interaction = None):
    """
    Performs the full refresh process. Can be called from on_ready or a slash command.
    """
    if VERBOSE_LOGGING:
        print("Starting automated refresh process.")
    
    deleted_count = 0
    created_count = 0

    # Step 1: Fetch roles.txt file from GitHub.
    roles_file_path = os.path.join(DATA_DIR, "roles.txt")
    fetch_file(ROLES_URL, roles_file_path)
    if VERBOSE_LOGGING:
        print("Step 1 complete: roles.txt fetched from GitHub.")
    await asyncio.sleep(1)

    # Step 2: Delete old messages based on IDs from the fetched file.
    parsed_data = _get_parsed_data(roles_file_path)
    for channel_id, config in parsed_data.items():
        if config["message_id"]:
            channel = bot_instance.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(config["message_id"])
                    await message.delete()
                    deleted_count += 1
                    if VERBOSE_LOGGING:
                        print(f"Deleted old message with ID: {config['message_id']} from channel {channel.name}")
                except discord.NotFound:
                    if VERBOSE_LOGGING:
                        print(f"Message with ID {config['message_id']} not found. Skipping deletion.")
                except Exception as e:
                    print(f"Error deleting message: {e}")
    if VERBOSE_LOGGING:
        print(f"Step 2 complete: {deleted_count} old messages deleted.")
    await asyncio.sleep(1)

    # Step 3: Clean up the local roles.txt file.
    bot_instance._unmark_all_blocks()
    if VERBOSE_LOGGING:
        print("Step 3 complete: Local roles.txt cleaned.")
    await asyncio.sleep(1)

    # Step 4: Run the rolesilent command logic to create new messages.
    # We pass None for the interaction and True for is_ephemeral, but it will be ignored.
    await _process_roles_messages(interaction, True)

    # Count messages created by _process_roles_messages
    new_parsed_data = _get_parsed_data(roles_file_path)
    for config in new_parsed_data.values():
        if config["message_id"]:
            created_count += 1
    if VERBOSE_LOGGING:
        print(f"Step 4 complete: {created_count} new messages created.")

    # Step 5: The _process_roles_messages function handles the final push to GitHub.
    if VERBOSE_LOGGING:
        print("Step 5 is part of the previous step. Process complete.")
    
    # Send a summary message based on the context (ephemeral for slash command)
    if interaction:
        await _send_refresh_summary(interaction, deleted_count, created_count, ephemeral=True)
    else:
        await _send_refresh_summary(bot_instance, deleted_count, created_count)


async def _send_refresh_summary(target, deleted_count, created_count, ephemeral=False):
    """
    Sends a summary message and purges temporary bot output.
    `target` can be an `interaction` or a `bot_instance`.
    """
    try:
        if isinstance(target, discord.Interaction):
            # Send an ephemeral summary message for slash commands
            await target.followup.send(
                f"Role messages have been refreshed successfully.\n"
                f"**{deleted_count}** old messages deleted.\n"
                f"**{created_count}** new messages created.",
                ephemeral=ephemeral
            )
        elif isinstance(target, commands.Bot):
            # Purge all bot messages in the admin channel before sending the final summary
            admin_channel = target.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                await admin_channel.purge(check=lambda m: m.author == target.user)

                await admin_channel.send(
                    f"Role messages have been refreshed successfully.\n"
                    f"**{deleted_count}** old messages deleted.\n"
                    f"**{created_count}** new messages created."
                )
    except Exception as e:
        if VERBOSE_LOGGING:
            print(f"Error sending refresh summary: {e}")


async def _log_command_usage(interaction: discord.Interaction):
    """
    Logs command usage to a specified bot output channel.
    """
    command_name = interaction.command.name
    
    # Do not log the verify command
    if command_name == "verify":
        return
        
    try:
        channel_id = BOT_OUTPUT_CHANNEL_ID
        log_channel = bot.get_channel(channel_id)
        if log_channel:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = (
                f"**Command Used:** `/{command_name}`\n"
                f"**User:** {interaction.user.mention} ({interaction.user.id})\n"
                f"**Channel:** {interaction.channel.mention} ({interaction.channel.id})\n"
                f"**Time:** `{timestamp}`"
            )
            # Make sure this message is not ephemeral.
            await log_channel.send(log_message)
    except Exception as e:
        if VERBOSE_LOGGING:
            print(f"Error logging command usage: {e}")


async def _send_startup_message(bot_instance):
    """
    Sends a direct message to a target user on bot startup.
    """
    try:
        target_channel = bot_instance.get_channel(BOT_OUTPUT_CHANNEL_ID)
        if target_channel:
            # We can use a special format to ping a user.
            user_mention = f"<@{TARGET_USER_ID}>"
            message = (
                f"Hey {user_mention}, I had to reboot. Or I just came back online after a reboot. I am ready!"
            )
            await target_channel.send(message)
            if VERBOSE_LOGGING:
                print(f"Sent startup message to {target_channel.name}")
    except Exception as e:
        print(f"Error sending startup message: {e}")


bot = RulesBot()

@bot.tree.command(name="message", description="This will post a pre-defined message")
async def message(interaction: discord.Interaction):
    await _log_command_usage(interaction)
    await interaction.response.send_message("Fetching latest message from GitHub...", ephemeral=True)
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest message.txt from GitHub before reading it
    file_path = os.path.join(DATA_DIR, "message.txt")
    fetch_file(MESSAGE_URL, file_path)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.channel.send(f.read())
        await interaction.followup.send("Message sent successfully.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


@bot.tree.command(name="msgsilent", description="Posts a pre-defined message silently.")
@app_commands.default_permissions(manage_roles=True)
async def msgsilent(interaction: discord.Interaction):
    await _log_command_usage(interaction)
    await interaction.response.send_message("Posting message silently...", ephemeral=True)
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest message.txt from GitHub before reading it
    file_path = os.path.join(DATA_DIR, "message.txt")
    fetch_file(MESSAGE_URL, file_path)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            await interaction.channel.send(f.read())
        await interaction.followup.send("Message sent successfully.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


@bot.tree.command(name="rolemsg", description="This is to push the stored roles messages to the defined channels.")
@app_commands.default_permissions(manage_roles=True)
async def rolemsg(interaction: discord.Interaction):
    """
    Parses roles.txt and performs the configured actions.
    """
    await _log_command_usage(interaction)
    await interaction.response.send_message("Fetching latest roles file from GitHub...", ephemeral=True)
    await _process_roles_messages(interaction, False)


@bot.tree.command(name="rolesilent", description="This is to push the stored roles messages silently.")
@app_commands.default_permissions(manage_roles=True)
async def rolesilent(interaction: discord.Interaction):
    """
    Parses roles.txt and performs the configured actions silently.
    """
    await _log_command_usage(interaction)
    await interaction.response.send_message("Fetching latest roles file from GitHub and processing silently...", ephemeral=True)
    await _process_roles_messages(interaction, True)


@bot.tree.command(name="refreshrole", description="Refreshes all roles messages in all channels.")
@app_commands.default_permissions(manage_roles=True)
async def refreshrole(interaction: discord.Interaction):
    """
    Refreshes all roles messages in all channels.
    """
    await _log_command_usage(interaction)
    await interaction.response.defer(ephemeral=True)
    await _perform_refresh_task(bot, interaction)


@bot.tree.command(name="assistme", description="This will silently give you guidance on how to write the roles.txt file.")
@app_commands.default_permissions(manage_roles=True)
async def assistme(interaction: discord.Interaction):
    await _log_command_usage(interaction)
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


@bot.tree.command(name="clearchat", description="Deletes messages from the current channel.")
@app_commands.describe(count="The number of messages to delete, or 'all' to delete all.")
@app_commands.default_permissions(manage_messages=True)
async def clearchat(interaction: discord.Interaction, count: str):
    await _log_command_usage(interaction)
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Get the original response message to prevent it from being purged.
        original_message = await interaction.original_response()

        if count.lower() == "all":
            # Purge all messages before the original message.
            deleted = await interaction.channel.purge(before=original_message)
            await interaction.followup.send(f"Successfully deleted all messages in this channel.", ephemeral=True)
        else:
            try:
                limit = int(count)
                if limit <= 0:
                    await interaction.followup.send("Please provide a positive number of messages to delete.", ephemeral=True)
                    return
                # Purge a specific number of messages before the original message.
                deleted = await interaction.channel.purge(limit=limit, before=original_message)
                await interaction.followup.send(f"Successfully deleted **{len(deleted)}** messages.", ephemeral=True)
            except ValueError:
                await interaction.followup.send("Invalid input. Please provide a number or 'all'.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("I don't have the required permissions to delete messages.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        if VERBOSE_LOGGING:
            print(f"An error occurred during clear chat: {e}")


@bot.tree.command(name="verify", description="Placeholder command for verification.")
@app_commands.default_permissions(manage_roles=True)
async def verify(interaction: discord.Interaction):
    await interaction.response.send_message("This is a placeholder for the verify command.", ephemeral=True)


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
            if VERBOSE_LOGGING:
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
                        if VERBOSE_LOGGING:
                            print(f"Toggled off role {role.name} for {member.display_name}")
                    else:
                        # User does not have the role, so add it
                        await member.add_roles(role)
                        if VERBOSE_LOGGING:
                            print(f"Toggled on role {role.name} for {member.display_name}")
                else:
                    # Normal reaction role, add the role
                    await member.add_roles(role)
                    if VERBOSE_LOGGING:
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
            if VERBOSE_LOGGING:
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
                    if VERBOSE_LOGGING:
                        print(f"Removing role {role.name} from {member.display_name}")
                    await member.remove_roles(role)


if __name__ == "__main__":
    bot.run(TOKEN)
