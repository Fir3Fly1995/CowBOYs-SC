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
# Admin Channel and Target User ID variables will be loaded from BotVar.txt
ADMIN_CHANNEL_ID = None
TARGET_USER_ID = None

TOKEN = os.getenv("CRUEL_STARS_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://raw.githubusercontent.com/Fir3Fly1995/CowBOYs-SC/main/Mini-bot/Bot/"
REPO_API_URL = "https://api.github.com/repos/Fir3Fly1995/CowBOYs-SC/contents/Mini-bot/Bot/"
MESSAGE_URL = BASE_URL + "message.txt"
ROLES_URL = BASE_URL + "roles.txt"
INSTRUCTIONS_URL = BASE_URL + "instructions.txt"
CHANNELS_URL = BASE_URL + "channels.txt"
BOT_VAR_URL = BASE_URL + "BotVar.txt"
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
intents.message_content = True
intents.voice_states = True


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
        self.bot_var_file_path = os.path.join(DATA_DIR, "BotVar.txt")
        self.s_logs_file_path = os.path.join(DATA_DIR, "S_LOGS.txt")
        self.inf_file_path = os.path.join(DATA_DIR, "INF.txt")
        self.config = {}

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

        # Load configuration variables from BotVar.txt
        self.load_bot_vars()

        # Send a direct ping to the target user when the bot comes online.
        try:
            await _send_startup_message(self)
        except Exception as e:
            print(f"Error sending startup message: {e}")

        # On startup, run the rolemsg logic to update all messages.
        try:
            await _process_roles_messages(self, None, True)
        except Exception as e:
            print(f"Error running silent role message update: {e}")

    def load_bot_vars(self):
        """
        Loads and parses the BotVar.txt file to set global configuration variables.
        """
        global VERBOSE_LOGGING, ADMIN_CHANNEL_ID, TARGET_USER_ID

        if not os.path.exists(self.bot_var_file_path):
            print(f"BotVar.txt not found. Using default configurations.")
            return

        with open(self.bot_var_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        config = {}
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                config[key] = value
            except ValueError:
                print(f"Warning: Skipping malformed line in BotVar.txt: {line}")
        
        self.config['V_LOG'] = config.get('V_LOG', 'True').lower() == 'true'
        self.config['S_LOG'] = config.get('S_LOG', 'True').lower() == 'true'
        self.config['INF_LOG'] = config.get('INF_LOG', 'True').lower() == 'true'
        self.config['BOLD_WORD'] = [word.strip().lower() for word in config.get('BOLD_WORD', '').split(',') if word.strip()]
        
        try:
            ADMIN_CHANNEL_ID = int(config.get('ADMIN_CH', '0'))
            TARGET_USER_ID = int(config.get('USR_ID', '0'))
        except (ValueError, TypeError):
            print("Warning: ADMIN_CH or USR_ID in BotVar.txt is not a valid integer. Using default 0.")
            ADMIN_CHANNEL_ID = 0
            TARGET_USER_ID = 0

        VERBOSE_LOGGING = self.config['V_LOG']
        
        if VERBOSE_LOGGING:
            print("Bot configuration loaded:")
            for key, value in self.config.items():
                print(f"  {key}: {value}")
            print(f"  ADMIN_CHANNEL_ID: {ADMIN_CHANNEL_ID}")
            print(f"  TARGET_USER_ID: {TARGET_USER_ID}")

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

        # Split the content into individual blocks, keeping track of which are skipped
        block_matches = re.finditer(r'(Start\.|Skip\.)(.*?)(?=Start\.|Skip\.|\Z)', content, flags=re.DOTALL | re.IGNORECASE)

        parsed_data = {}
        for match in block_matches:
            block = match.group(2).strip()
            
            channel_id_match = re.search(r'CH-ID<#(\d+)>', block)
            message_id_match = re.search(r'MSG-ID:(\d+)', block)
            
            # Determine if the block is a toggle or static
            toggle_role_match = re.search(r'Toggle-Role', block, flags=re.IGNORECASE)
            static_role_match = re.search(r'Static-Role', block, flags=re.IGNORECASE)
            
            is_toggle = True # Default to Toggle-Role
            if static_role_match:
                is_toggle = False
            elif toggle_role_match:
                is_toggle = True

            message_text = None
            message_text_match = re.search(r'MSG;(.*?)(?:EMOTE_1|MK-BTN_1|$)', block, flags=re.DOTALL | re.IGNORECASE)
            if message_text_match:
                message_text = message_text_match.group(1).strip()

            emotes = {}
            emote_matches = re.finditer(r'EMOTE_(\d+);\s*(<.+?|.+?)\s*\"(.+?)\"', block, flags=re.IGNORECASE)
            for emote_match in emote_matches:
                emote = emote_match.group(2).strip()
                label = emote_match.group(3).strip()
                emote_number = emote_match.group(1)

                give_role_match = re.search(f'Give_Role_{emote_number};\s*\"(.+?)\"', block, flags=re.IGNORECASE)
                if give_role_match:
                    role_name = give_role_match.group(1).strip()
                    emotes[emote] = {"label": label, "role_name": role_name, "is_toggle": is_toggle}

            buttons = {}
            button_matches = re.finditer(r'MK-BTN_(\d+);\s*Colour=(\S+);\s*Emoji=(\S+);\s*Text=\"(.+?)\"', block, flags=re.IGNORECASE)
            for button_match in button_matches:
                button_number = button_match.group(1)
                color = button_match.group(2)
                emoji = button_match.group(3)
                text = button_match.group(4)
                
                give_role_matches = re.findall(f'Give_Role_{button_number};\s*\"(.+?)\"', block, flags=re.IGNORECASE)
                if give_role_matches:
                    role_names = [r.strip() for r in give_role_matches]
                    buttons[button_number] = {
                        "color": color.upper(),
                        "emoji": emoji,
                        "text": text,
                        "role_names": role_names,
                        "is_toggle": is_toggle
                    }


            if channel_id_match:
                channel_id = int(channel_id_match.group(1))
                message_id = int(message_id_match.group(1)) if message_id_match else None
                
                parsed_data[channel_id] = {
                    "message_id": message_id,
                    "message_text": message_text,
                    "emotes": emotes,
                    "buttons": buttons
                }

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
        and adding the message ID.
        """
        if not os.path.exists(self.roles_file_path):
            return

        with open(self.roles_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        block_pattern = re.compile(f'((Start|Skip)\\.\\s*\\n\\s*CH-ID<#({channel_id})>.*?\\n\\s*End\\.)', re.DOTALL | re.IGNORECASE)
        match = block_pattern.search(content)

        if not match:
            if VERBOSE_LOGGING:
                print(f"Block for channel {channel_id} not found in roles.txt. Cannot mark as skipped.")
            return

        full_block = match.group(0)
        
        # 1. Replace 'Start.' or 'Skip.' with 'Skip.'
        new_block = re.sub(r'^(Start|Skip)\.', 'Skip.', full_block, flags=re.IGNORECASE | re.MULTILINE)
        
        # 2. Remove any existing MSG-ID to prevent duplicates.
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

        roles_to_add = [discord.utils.get(guild.roles, name=role_name) for role_name in self.role_names]
        roles_to_add = [role for role in roles_to_add if role is not None]

        if not roles_to_add:
            await interaction.followup.send("One or more roles not found. Please contact an admin.", ephemeral=True)
            return

        if self.is_toggle:
            for role in roles_to_add:
                if role in member.roles:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)
            await interaction.followup.send(
                f"Roles updated: {', '.join([role.name for role in roles_to_add])}", ephemeral=True
            )
        else:
            added_roles = []
            for role in roles_to_add:
                if role not in member.roles:
                    await member.add_roles(role)
                    added_roles.append(role.name)
            
            if "Rules Accepted" in added_roles:
                await interaction.followup.send(
                    "Thanks for accepting the rules. Please go to channel <#1404524826978287816> and say hi! :) ", 
                    ephemeral=True
                )
            elif added_roles:
                await interaction.followup.send(
                    f"You have been given the roles: {', '.join(added_roles)}", ephemeral=True
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
        
        parsed_data = self.bot.load_reaction_roles()
        
        for _, config in parsed_data.items():
            if config["buttons"]:
                for _, btn_data in config["buttons"].items():
                    custom_id = f"role_button:{';'.join(btn_data['role_names'])}:{btn_data['is_toggle']}"
                    
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
        
        custom_id_parts = button.custom_id.split(':')
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user

        role_names_str = custom_id_parts[3]
        is_toggle = custom_id_parts[4].lower() == 'true'
        role_names = role_names_str.split(';')
        
        roles_to_add = [discord.utils.get(guild.roles, name=role_name) for role_name in role_names]
        roles_to_add = [role for role in roles_to_add if role is not None]

        if not roles_to_add:
            await interaction.followup.send("One or more roles not found. Please contact an admin.", ephemeral=True)
            return
            
        if is_toggle:
            for role in roles_to_add:
                if role in member.roles:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)
            await interaction.followup.send(
                f"Roles updated: {', '.join([role.name for role in roles_to_add])}", ephemeral=True
            )
        else:
            added_roles = []
            for role in roles_to_add:
                if role not in member.roles:
                    await member.add_roles(role)
                    added_roles.append(role.name)

            if "Rules Accepted" in added_roles:
                await interaction.followup.send(
                    "Thanks for accepting the rules. Please go to channel <#1404524826978287816> and say hi! :) ", 
                    ephemeral=True
                )
            elif added_roles:
                await interaction.followup.send(
                    f"You have been given the roles: {', '.join(added_roles)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "You already have all the roles.", ephemeral=True
                )

async def _process_roles_messages(bot_instance, interaction: discord.Interaction = None, is_ephemeral: bool = False):
    """
    Core logic for creating/updating roles messages.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    file_path = os.path.join(DATA_DIR, "roles.txt")
    fetch_file(ROLES_URL, file_path)
    
    parsed_data = bot_instance.load_reaction_roles()
    if not parsed_data:
        if interaction:
            await interaction.followup.send("Could not parse roles.txt or file is empty.", ephemeral=is_ephemeral)
        return

    for channel_id, config in parsed_data.items():
        channel = bot_instance.get_channel(channel_id)
        if not channel:
            if VERBOSE_LOGGING:
                print(f"Channel with ID {channel_id} not found.")
            continue
        
        message_to_update = None
        new_message_id = None
        
        if config["message_id"]:
            try:
                message_to_update = await channel.fetch_message(config["message_id"])
                if VERBOSE_LOGGING:
                    print(f"Found existing message with ID {config['message_id']}. Attempting to update it.")
            except discord.NotFound:
                if VERBOSE_LOGGING:
                    print(f"Message with ID {config['message_id']} not found. Will create a new one.")
                config["message_id"] = None
                
            except Exception as e:
                print(f"Error fetching message: {e}")
                continue
        
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
            await message_to_update.edit(content=config["message_text"], view=view)
            new_message_id = message_to_update.id
            if VERBOSE_LOGGING:
                print(f"Updated existing message with ID: {new_message_id}")
        else:
            reaction_message = await channel.send(
                content=config["message_text"],
                view=view
            )
            new_message_id = reaction_message.id
            if VERBOSE_LOGGING:
                print(f"New message created with ID: {new_message_id}")
            
        message_to_react = await channel.fetch_message(new_message_id)
        if message_to_react:
            for emote in config["emotes"]:
                try:
                    await message_to_react.add_reaction(emote)
                except discord.HTTPException as e:
                    print(f"Error adding reaction {emote}: {e}")
                    print("This is likely due to an invalid emoji format in your roles.txt file.")
                    print("Please ensure you are using a raw unicode emoji or the full custom emoji format (<:name:id>).")
                    
        bot_instance._mark_block_as_skipped(channel_id, new_message_id)

    update_github_file(file_path, "Bot updated roles.txt with new message IDs")

    if interaction:
        await interaction.followup.send("Roles messages have been processed.", ephemeral=is_ephemeral)


async def _send_startup_message(bot_instance):
    """
    Sends a direct message to a target user on bot startup.
    """
    await bot_instance.wait_until_ready()
    try:
        if TARGET_USER_ID:
            target_user = await bot_instance.fetch_user(TARGET_USER_ID)
            if target_user:
                message = (
                    f"Hey, I had to reboot. Or I just came back online after a reboot. I am ready!"
                )
                await target_user.send(message)
                if VERBOSE_LOGGING:
                    print(f"Sent startup message to {target_user.name}")
    except Exception as e:
        print(f"Error sending startup message: {e}")


def _write_to_log_file(filepath, log_message):
    """
    Writes a timestamped message to a log file.
    """
    try:
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} {log_message}\n")
    except Exception as e:
        print(f"Error writing to log file {filepath}: {e}")


bot = RulesBot()

@bot.tree.command(name="message", description="This will post a pre-defined message")
async def message(interaction: discord.Interaction):
    await interaction.response.send_message("Fetching latest message from GitHub...", ephemeral=True)
    os.makedirs(DATA_DIR, exist_ok=True)
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
    await interaction.response.send_message("Fetching latest roles file from GitHub...", ephemeral=True)
    await _process_roles_messages(bot, interaction, False)


@bot.tree.command(name="refreshrole", description="Refreshes all roles messages in all channels.")
@app_commands.default_permissions(manage_roles=True)
async def refreshrole(interaction: discord.Interaction):
    """
    Refreshes all roles messages in all channels.
    """
    await interaction.response.defer(ephemeral=True)
    await _process_roles_messages(bot, interaction, True)


@bot.tree.command(name="assistme", description="This will silently give you guidance on how to write the roles.txt file.")
@app_commands.default_permissions(manage_roles=True)
async def assistme(interaction: discord.Interaction):
    await interaction.response.send_message("Fetching instructions...", ephemeral=True)
    os.makedirs(DATA_DIR, exist_ok=True)
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
    await interaction.response.defer(ephemeral=True)
    
    try:
        original_message = await interaction.original_response()

        if count.lower() == "all":
            deleted = await interaction.channel.purge(before=original_message)
            await interaction.followup.send(f"Successfully deleted all messages in this channel.", ephemeral=True)
        else:
            try:
                limit = int(count)
                if limit <= 0:
                    await interaction.followup.send("Please provide a positive number of messages to delete.", ephemeral=True)
                    return
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
                        await member.remove_roles(role)
                        if VERBOSE_LOGGING:
                            print(f"Toggled off role {role.name} for {member.display_name}")
                    else:
                        await member.add_roles(role)
                        if VERBOSE_LOGGING:
                            print(f"Toggled on role {role.name} for {member.display_name}")
                else:
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

            if is_toggle:
                role_name = role_data.get("role_name")
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role is not None:
                    if VERBOSE_LOGGING:
                        print(f"Removing role {role.name} from {member.display_name}")
                    await member.remove_roles(role)


# --- Event Listeners for Logging ---
@bot.listen()
async def on_voice_state_update(member, before, after):
    """
    Logs voice channel joins and leaves.
    """
    # Check if a voice channel change occurred.
    if before.channel == after.channel:
        return

    log_message = None
    if after.channel is not None:
        log_message = f"{member.display_name} has entered voice channel {after.channel.name}"
        output_message = f"**{member.display_name}** has entered voice channel {after.channel.mention}"
    elif before.channel is not None:
        log_message = f"{member.display_name} has left voice channel {before.channel.name}"
        output_message = f"**{member.display_name}** has left voice channel {before.channel.mention}"

    if log_message and bot.config.get('S_LOG', False):
        _write_to_log_file(bot.s_logs_file_path, log_message)

    if output_message and ADMIN_CHANNEL_ID:
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(output_message)


@bot.listen()
async def on_message_delete(message):
    """
    Logs deleted messages to the appropriate channel and file.
    """
    if message.author.bot:
        return
    
    # Check if the message was deleted in the admin channel
    if message.channel.id == ADMIN_CHANNEL_ID and TARGET_USER_ID:
        log_channel = bot.get_user(TARGET_USER_ID)
    else:
        log_channel = bot.get_channel(ADMIN_CHANNEL_ID)

    if not log_channel:
        return

    # Find who deleted the message by checking the audit log
    deleter = None
    try:
        async for entry in message.guild.audit_logs(limit=2, action=discord.AuditLogAction.message_delete):
            if entry.target.id == message.author.id:
                deleter = entry.user
                break
    except discord.Forbidden:
        if VERBOSE_LOGGING:
            print("Bot lacks permissions to view audit log.")
    except Exception as e:
        if VERBOSE_LOGGING:
            print(f"Error fetching audit log: {e}")

    # Prepare the log message content
    deleter_name = deleter.display_name if deleter else "Unknown"
    log_content = message.content or "(Content not available)"

    file_log_message = f"Message by {message.author.display_name} was deleted by {deleter_name} in channel {message.channel.name}. Content: {log_content}"
    output_log_message = f"**Message deleted by {deleter_name}**\n" \
                         f"> **Author:** {message.author.display_name}\n" \
                         f"> **Channel:** {message.channel.mention}\n" \
                         f"> **Content:** {log_content}"

    if bot.config.get('S_LOG', False):
        _write_to_log_file(bot.s_logs_file_path, file_log_message)

    await log_channel.send(output_log_message)


@bot.listen()
async def on_message(message):
    """
    Checks for bold words and logs infractions.
    """
    if message.author.bot:
        return

    if not bot.config.get('INF_LOG', False):
        return
    
    if not bot.config.get('BOLD_WORD', []):
        return

    content_lower = message.content.lower()
    found_infraction = False
    for word in bot.config['BOLD_WORD']:
        if re.search(r'\b' + re.escape(word) + r'\b', content_lower):
            found_infraction = True
            break
    
    if found_infraction:
        log_message = f"Infraction by {message.author.display_name} in channel {message.channel.name}. Content: {message.content}"
        _write_to_log_file(bot.inf_file_path, log_message)

        if ADMIN_CHANNEL_ID:
            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                infraction_embed = discord.Embed(
                    title="Infraction Detected",
                    description=f"A bold word was found in a message.",
                    color=discord.Color.red()
                )
                infraction_embed.add_field(name="Author", value=message.author.mention, inline=False)
                infraction_embed.add_field(name="Channel", value=message.channel.mention, inline=False)
                infraction_embed.add_field(name="Content", value=f"```\n{message.content}\n```", inline=False)
                await admin_channel.send(embed=infraction_embed)


if __name__ == "__main__":
    bot.run(TOKEN)
