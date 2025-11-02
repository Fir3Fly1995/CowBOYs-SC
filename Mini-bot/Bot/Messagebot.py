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
import random
import string # Required for generating the verification code


# --- Logging and GitHub Integration ---
# Set to True for verbose console output, False to disable.
VERBOSE_LOGGING = True
# Replace with the actual ID of your admin channel.
ADMIN_CHANNEL_ID = 1408438877278175272
# Replace with your User ID for direct pings.
TARGET_USER_ID = 470337413923995675

# --- RSI Verification Setup ---
# The VARIABLE part of your RSI Org URL. E.g., for '.../orgs/CSSTAR/members', this is 'CSSTAR'.
RSI_ORG_VARIABLE = "SPBOYS" 
# The name of the role members receive upon successful verification.
VERIFIED_ROLE_NAME = "Verified" 
# New role whose members are protected from name spoofing.
ADMIN_PROTECTED_ROLE_NAME = "Founder"

# Verification codes are now stored in memory (self.pending_verifications) and reset on bot restart.

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
        "Accept": "application/vnd.github.com"
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
        "Accept": "application/vnd.github.com"
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

def generate_verification_code(length=6):
    """Generates a random, six-character alphanumeric string."""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))


# We need to enable specific intents for reactions and members
# This tells Discord that your bot needs to listen for these events.
intents = discord.Intents.default()
intents.reactions = True
intents.members = True
intents.message_content = True


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
        # In-memory store for pending verification codes {user_id (str): (code: str, timestamp: datetime.datetime)}
        self.pending_verifications = {} 

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
        try:
            await _send_startup_message(self)
        except Exception as e:
            print(f"Error sending startup message: {e}")

        # On startup, run the rolemsg logic to update all messages.
        try:
            await _process_roles_messages(self, None, True)
        except Exception as e:
            print(f"Error running silent role message update: {e}")

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
            block_type = match.group(1).strip().lower()
            block = match.group(2).strip()
            
            # Use a more robust regex to find all the different parts of the block.
            # This is the crucial fix for the "could not parse" error.
            channel_id_match = re.search(r'CH-ID<#(\d+)>', block)
            message_id_match = re.search(r'MSG-ID:(\d+)', block)
            replace_msg = "Replace_MSG" in block

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

                is_toggle = False
                toggle_role_match = re.search(f'Toggle-Role', block, flags=re.IGNORECASE)
                if toggle_role_match:
                    is_toggle = True

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
                
                is_toggle = False
                toggle_role_match = re.search(f'Toggle-Role', block, flags=re.IGNORECASE)
                if toggle_role_match:
                    is_toggle = True

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

    def get_all_button_configs(self):
        """Fetches all button configurations from all blocks in roles.txt for reconstruction."""
        # This function fetches configs to reconstruct the persistent view on startup
        parsed_data = self.load_reaction_roles()
        all_buttons = []
        # Use a map to store unique custom_ids to prevent duplicates
        unique_buttons = {} 
        
        for _, config in parsed_data.items():
            if config["buttons"]:
                for _, btn_data in config["buttons"].items():
                    # Construct the unique custom_id exactly as done in _process_roles_messages
                    custom_id = f"{btn_data['color']}:{btn_data['emoji']}:{btn_data['text']}:{';'.join(btn_data['role_names'])}:{btn_data['is_toggle']}"
                    
                    if custom_id not in unique_buttons:
                        unique_buttons[custom_id] = {
                            "style": RoleButton.COLOR_MAP.get(btn_data['color'].lower(), discord.ButtonStyle.secondary),
                            "emoji": btn_data['emoji'],
                            "label": btn_data['text'],
                            "custom_id": custom_id,
                        }

        return list(unique_buttons.values())


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
        
        # 3. Remove any existing Replace_MSG lines.
        new_block = re.sub(r'Replace_MSG\s*\n', '', new_block, flags=re.IGNORECASE)

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
        # Custom ID must be a single string. It's built in RoleView.
        # This implementation uses the class method which is deprecated but functional if the custom_id is set.
        super().__init__(style=style, emoji=emoji, label=text)
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
            
            # Check if the "Rules Accepted" role was among the added roles
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
        self.reconstruct_buttons() # FIX: Reconstruct buttons for persistence

    def reconstruct_buttons(self):
        """Dynamically reconstructs and adds persistent buttons to the view on startup."""
        
        # Clear any items added by the decorator or previous runs
        self.clear_items()
        
        # Use the new method to get all necessary button data
        button_configs = self.bot.get_all_button_configs()
        
        for btn_config in button_configs:
            # We must use the exact style, label, emoji, and custom_id used when the message was sent.
            button = discord.ui.Button(
                style=btn_config['style'],
                emoji=btn_config['emoji'],
                label=btn_config['label'],
                custom_id=btn_config['custom_id']
            )
            # Create a proper callback that captures the interaction
            async def button_callback(interaction: discord.Interaction, btn=button):
                await self.dynamic_callback(interaction)
            
            button.callback = button_callback
            self.add_item(button)
            
    # REMOVED: @discord.ui.button decorator so this method can serve as the universal callback
    async def dynamic_callback(self, interaction: discord.Interaction):
        """Handle dynamic button callbacks."""
        
        # Acknowledge the interaction immediately.
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Custom ID format: "COLOR:EMOJI:TEXT:ROLE_NAMES_LIST:IS_TOGGLE"
            custom_id_parts = interaction.data['custom_id'].split(':')
            
            if len(custom_id_parts) < 5:
                await interaction.followup.send("Button data is corrupt (too few parts). Contact admin.", ephemeral=True)
                return

            guild = interaction.guild
            member = interaction.user

            # Extract data from the custom_id
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

                # Check if the "Rules Accepted" role was among the added roles
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
        
        except Exception as e:
            error_msg = f"An error occurred during button callback: {e} | Custom ID: {interaction.data['custom_id']}"
            print(error_msg)
            
            admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                await admin_channel.send(f"⚠️ **Button Error:** {interaction.user.mention} clicked a button resulting in an error. Details: `{error_msg}`")
                
            # Send a generic error to the user
            await interaction.followup.send("An unexpected error occurred processing your request. Admins have been notified.", ephemeral=True)

async def _process_roles_messages(bot_instance, interaction: discord.Interaction = None, is_ephemeral: bool = False):
    """
    Core logic for creating/updating roles messages.
    """
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    # Fetch the latest roles.txt from GitHub before processing it
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
        view = RoleView(bot_instance)  # Use the bot's persistent view
        
        if config["buttons"]:
            # Clear existing items and add new ones
            view.clear_items()
            for _, btn_data in config["buttons"].items():
                # Manually construct the custom_id for persistent views
                custom_id = f"{btn_data['color']}:{btn_data['emoji']}:{btn_data['text']}:{';'.join(btn_data['role_names'])}:{btn_data['is_toggle']}"
                
                button = discord.ui.Button(
                    style=RoleButton.COLOR_MAP.get(btn_data['color'].lower(), discord.ButtonStyle.secondary),
                    emoji=btn_data['emoji'],
                    label=btn_data['text'],
                    custom_id=custom_id # Set the custom ID here
                )
                # Bind the callback properly
                async def button_callback(interaction: discord.Interaction, btn=button):
                    await view.dynamic_callback(interaction)
                
                button.callback = button_callback
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
        bot_instance._mark_block_as_skipped(channel_id, new_message_id)

    update_github_file(file_path, "Bot updated roles.txt with new message IDs")

    if interaction:
        await interaction.followup.send("Roles messages have been processed.", ephemeral=is_ephemeral)


async def _send_startup_message(bot_instance):
    """
    Sends a direct message to a target user on bot startup.
    """
    # Wait until the bot is fully ready and has its cache loaded
    await bot_instance.wait_until_ready()
    try:
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


bot = RulesBot()

@bot.tree.command(name="message", description="This will post a pre-defined message")
async def message(interaction: discord.Interaction):
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


@bot.tree.command(name="verify", description="Verifies your RSI username using Org or Bio check.")
@app_commands.describe(rsi_username="Your exact RSI Citizen or Handle name.")
async def verify(interaction: discord.Interaction, rsi_username: str):
    await interaction.response.defer(ephemeral=True)
    member = interaction.user
    guild = interaction.guild
    
    # --- LOGGING SETUP ---
    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    if admin_channel:
        # Initial log message for every attempt
        await admin_channel.send(f"🕵️ **Verification Attempt Started** by {member.mention} (Discord ID: `{member.id}`). RSI Name: `{rsi_username}`.")

    # --- ROLE SETUP ---
    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    admin_protected_role = discord.utils.get(guild.roles, name=ADMIN_PROTECTED_ROLE_NAME)
    
    if not verified_role:
        await interaction.followup.send("Error: The Verified role is misconfigured. Please contact an admin.", ephemeral=True)
        return

    # --- ANTI-SPOOFING PRE-CHECK ---
    check_name_lower = rsi_username.lower()
    protected_roles = [r for r in [verified_role, admin_protected_role] if r]
    
    if protected_roles:
        async for guild_member in guild.fetch_members(limit=None):
            
            if guild_member.id == member.id:
                continue
                
            is_protected = any(role in guild_member.roles for role in protected_roles)
            
            if is_protected:
                
                member_name_to_check = guild_member.display_name.lower()
                member_username_to_check = guild_member.name.lower()

                if member_name_to_check == check_name_lower or member_username_to_check == check_name_lower:
                    
                    alert_role = next((role.name for role in protected_roles if role in guild_member.roles), VERIFIED_ROLE_NAME)

                    # Send urgent admin log message
                    if admin_channel:
                        await admin_channel.send(
                            f"🚨 **SECURITY ALERT - SPOOFING BLOCKED!**\n"
                            f"**Attempted User:** {member.mention}\n"
                            f"**RSI Name Used:** `{rsi_username}`\n"
                            f"**Protected User:** {guild_member.mention} (Role: **@{alert_role}**)"
                        )

                    await interaction.followup.send(
                        f"❌ **Spoofing Alert!** The RSI handle `{rsi_username}` is already claimed and protected "
                        f"by a member with the **@{alert_role}** role. Verification aborted.",
                        ephemeral=True
                    )
                    return
    # --- END ANTI-SPOOFING PRE-CHECK ---

    # Helper function to assign roles and nickname
    async def complete_verification():
        log_status = "SUCCESS"
        try:
            # 1. Assign Roles (only Verified is needed now)
            await member.add_roles(verified_role)
            
            # 2. Change Nickname
            try:
                # Max nickname length is 32 characters in Discord
                nick_to_set = rsi_username[:32] 
                await member.edit(nick=nick_to_set)
                nickname_message = f"and your nickname has been set to `{nick_to_set}`."
            except discord.Forbidden:
                nickname_message = "(I couldn't change your server nickname due to missing permissions.)"

            await interaction.followup.send(
                f"🎉 **Verification Complete!** Your new role is **{verified_role.name}** {nickname_message}",
                ephemeral=True
            )
            if VERBOSE_LOGGING:
                 print(f"Verification successful for {member.display_name}. RSI: {rsi_username}")

        except discord.Forbidden:
            log_status = "ERROR (Forbidden Role/Nick)"
            await interaction.followup.send(
                "Verification succeeded, but I failed to update your role or nickname due to permission issues. Please contact an anmin.",
                ephemeral=True
            )
        except Exception as e:
            log_status = f"ERROR ({type(e).__name__})"
            await interaction.followup.send(f"An unexpected error occurred during role assignment: {e}", ephemeral=True)

        if admin_channel:
            await admin_channel.send(f"✅ **Verification Complete:** {member.mention} ({rsi_username}). **Status:** {log_status}.")


    # --- Step 1: Check Org Member List (Primary Check) ---
    org_url = f"https://www.robertsspaceindustries.com/orgs/{RSI_ORG_VARIABLE}/members"
    try:
        # Check if the RSI username is in the Org member list
        org_response = requests.get(org_url, timeout=10)
        org_response.raise_for_status()
        
        # --- FIX: Targeting the specific '/citizens/username' href link, case-insensitive ---
        # The expected link structure is '/citizens/{username}' (as found via inspect element)
        search_term = f'/citizens/{rsi_username}'.lower() 
        if search_term in org_response.text.lower():
            await interaction.followup.send(
                f"**Verification Success (Org Check)!** Found `{rsi_username}` in the **{RSI_ORG_VARIABLE}** member list.", 
                ephemeral=True
            )
            # If found, skip the bio check and complete verification
            await complete_verification()
            return
            
    except requests.RequestException as e:
        # Log the failure for debugging, and provide context about the scraping method
        print(f"Org Check Failure (Expected): The basic Org member list scrape failed for {org_url}. This is common with dynamic RSI pages. Proceeding to Bio Check. Error: {e}")
        # Continue to the Bio check on error/failure

    # --- Step 2: Check Bio Code (Secondary Check/Fallback) ---
    user_id_str = str(member.id)
    # URL for public viewing/scraping the bio
    citizen_url = f"https://www.robertsspaceindustries.com/citizens/{rsi_username}"
    # URL for user instruction to edit the bio (The corrected URL)
    account_url = "https://www.robertsspaceindustries.com/account/profile"
    
    # 1 hour expiration window
    ONE_HOUR = datetime.timedelta(hours=1) 

    # Case 2a: User has a pending code - Check their bio now
    if user_id_str in bot.pending_verifications:
        code, timestamp = bot.pending_verifications[user_id_str]
        
        # Check for code expiration
        time_elapsed = datetime.datetime.now() - timestamp
        if time_elapsed > ONE_HOUR:
            del bot.pending_verifications[user_id_str]
            
            # Admin Log: Code Expired
            if admin_channel:
                await admin_channel.send(f"⚠️ **Verification Failed:** {member.mention} ({rsi_username}). **Status:** Code expired.")

            await interaction.followup.send(
                f"❌ Verification code for `{rsi_username}` has **expired** (>{ONE_HOUR} old).\n"
                f"Please run `/verify {rsi_username}` again to generate a new code.",
                ephemeral=True
            )
            return

        # Code is still valid, proceed with checking the RSI bio
        try:
            citizen_response = requests.get(citizen_url, timeout=10)
            citizen_response.raise_for_status()
            
            # Check for the code in the HTML response text (This MUST remain case-sensitive for the code)
            if code in citizen_response.text:
                # Verification succeeded via Bio Code!
                del bot.pending_verifications[user_id_str]
                await interaction.followup.send(
                    f"✅ **Verification Success (Bio Check)!** The code **`{code}`** was found in your RSI Bio at {citizen_url}.",
                    ephemeral=True
                )
                await complete_verification()
                return
            else:
                # Code not found yet
                time_remaining = ONE_HOUR - time_elapsed
                minutes_remaining = int(time_remaining.total_seconds() // 60)
                
                # Admin Log: Bio Code Not Found
                if admin_channel:
                    await admin_channel.send(f"🔄 **Verification Retried:** {member.mention} ({rsi_username}). **Status:** Bio code not yet found (Code: `{code}`).")

                await interaction.followup.send(
                    f"❌ Verification failed for `{rsi_username}`.\n"
                    f"I did not find the active code **`{code}`** in your public RSI Bio at {citizen_url}.\n"
                    f"Please ensure it is correctly placed and try the command again. The code expires in: **{minutes_remaining} minutes**."
                )
                return
                
        except requests.RequestException as e:
            # Admin Log: Request Error
            if admin_channel:
                await admin_channel.send(f"❌ **Verification Failed:** {member.mention} ({rsi_username}). **Status:** RSI profile access error.")

            await interaction.followup.send(
                f"❌ Verification failed: Could not access the public RSI profile page for `{rsi_username}` ({citizen_url}). "
                f"Please ensure the username is correct and the profile is public."
            )
            return

    # Case 2b: User has no pending code or Org lookup failed - Generate one
    else:
        new_code = generate_verification_code()
        # Store the new code with its creation time
        bot.pending_verifications[user_id_str] = (new_code, datetime.datetime.now())
        
        # Admin Log: New Code Issued
        if admin_channel:
            await admin_channel.send(f"➡️ **Verification Fallback:** {member.mention} ({rsi_username}). **Status:** Issued new bio code: `{new_code}`.")
        
        await interaction.followup.send(
            f"⚠️ **Org/Direct lookup failed.**\n"
            f"We need to verify you using your RSI Bio. Your unique verification code is:\n"
            f"**`{new_code}`**\n\n"
            f"**Steps to complete verification:**\n"
            f"1. Go to your **Account Profile** page to edit your bio: **{account_url}**\n" # Updated URL
            f"2. Paste the code **`{new_code}`** into your **Short Bio** (Dossier).\n"
            f"3. Come back to Discord and run `/verify {rsi_username}` again. "
            f"The code will expire in **1 hour**.",
            ephemeral=True
        )


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

            # --- This is the fix ---
            if is_toggle:
                role_name = role_data.get("role_name")
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role is not None:
                    # If it's a toggle role, we don't handle the reaction removal 
                    # as a role removal to simplify the interaction, as toggle is best
                    # done by re-adding the reaction.
                    pass 
            else:
                # Non-toggle role, remove it when the reaction is removed.
                role_name = role_data.get("role_name")
                role = discord.utils.get(guild.roles, name=role_name)
                if role is not None:
                    await member.remove_roles(role)
                    if VERBOSE_LOGGING:
                        print(f"Removing non-toggle role {role.name} from {member.display_name} via reaction remove.")


# --- New Event Listeners for Logging ---
@bot.listen()
async def on_voice_state_update(member, before, after):
    """
    Logs voice channel joins and leaves to the ADMIN_CHANNEL_ID.
    """
    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    if not admin_channel:
        return

    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        await admin_channel.send(f"**{member.display_name}** has entered voice channel {after.channel.mention}")

    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        await admin_channel.send(f"**{member.display_name}** has left voice channel {before.channel.mention}")


@bot.listen()
async def on_message_delete(message):
    """
    Logs deleted messages to the ADMIN_CHANNEL_ID.
    Note: This only works for messages in the bot's cache.
    """
    # Don't log bot messages
    if message.author.bot:
        return
        
    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    if not admin_channel:
        return

    # Find who deleted the message by checking the audit log
    deleter = None
    try:
        async for entry in message.guild.audit_logs(limit=2, action=discord.AuditLogAction.message_delete):
            if entry.target.id == message.author.id:
                deleter = entry.user
                break
    except discord.Forbidden:
        # The bot lacks the "View Audit Log" permission
        if VERBOSE_LOGGING:
            print("Bot lacks permissions to view audit log.")
    except Exception as e:
        if VERBOSE_LOGGING:
            print(f"Error fetching audit log: {e}")

    # Prepare the log message content
    if deleter:
        log_message = f"**Message deleted by {deleter.display_name}**\n"
    else:
        log_message = "**A message was deleted**\n"
    
    log_message += f"> **Author:** {message.author.mention}\n"
    log_message += f"> **Channel:** {message.channel.mention}\n"
    
    # Check if the message content is available (i.e., it was in the bot's cache)
    if message.content:
        log_message += f"> **Content:** {message.content}"
    else:
        log_message += "> **Content:** (Content not available, message not in bot's cache)"

    await admin_channel.send(log_message)


if __name__ == "__main__":
    bot.run(TOKEN)
