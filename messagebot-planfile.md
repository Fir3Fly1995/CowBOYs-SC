# Bot Planfile for syntax, and full rebuild for correct operation. 

## Stage 1: The Initial Build

1. Create the flags and instructions for the bot to function as desired. These instructions should be clear and concise, and they should be useful for the individual programming the bot. 
2. Split the core functions of the bot into multiple components, the fetch, commander, verifier and ranker pieces as separate .py scripts will all communicate with each other. However, they will all act separately and like individuals using the BotInterface script that will take slash commands, translate them into what script is used and what args are used, before passing it back to the interface for the return to Discord. 
3. We use roles.txt for the /sendmessage command and the /sendroles command. 
4. We use a .xlsx spreadsheet for the /Verify command so that when a user intends to verify they are from Star Cotizen, we can retain the Star Citizen username, the randomised code issued to them and their Discord Username. This way we will be able to identify a player even if their Discord Username differs from their RSI Profile. For GDPR purposes, this is the only information we are allowed to store and the .xlsx file will be added to .gitignore.
5. Redesign the entire Regex flags and matching system to be easier to use and faster to type, without getting repetitive and create a small .exe program that will enable the super speedy creation of a roles.txt file. 


## Stage 2: The .txt file flags

* start;
	* The natural start of the block.
* ch-id;xxxxxxxxxxx
	* Used to identify what channel a message is going into. The bot should automatically identify this flag and append > and prepend <# so it can accurately identify the channel ID.
* msg-id;xxxxxxxxxxx
	* Identifier for any pre-existing message made by the bot.
* reactid-x;xxxxxxxxxxx
	* The -x refers to a specific reaction identifier that's been posted by the /sendroles command.
* bttnid-x;xxxxxxxxx
	* The -x refers to the specific button identifier of a message posted by the /sendroles command.
* Msg-start;
	* This is where the user will type out their message for either the /send message or /sendroles command. All Text after this piece and before the next one on the list is treated as UTF-8 text and will be displayed in Discord as if it was written by a person.
* msg-end;
	* This is the natural conclusion of a message block.
* btn-x; colour, emoji, text
	* this creates a button. User can chose between red, green, blue, blurple and gray/grey . 
	* user should ensure that the emoji is directly copied from Discord. 
	* user should only have to state the colour of the button.
	* user should only have to type in the message for the button.
* react-x; EMOJI or :EMOJI_NAME:EMOJI_ID
	* User replaces x with a number, EMOJI is copied from Discord into the .txt file. 
	* If it's a custom emoji, the user must insert the emoji name between : and : then the emoji ID, no spaces allowed.
* data;
	* User enters the data; flag, this tells the /sendroles command where it can stash data relating to buttons and reaction roles, in the event that the bot has to be restarted.
* end;
	* User places the end flag at the bottom of their block. This signals that they are done with this block.
	* User leaves a blank line after this, then goes back to the top of the list with the start; flag.

## Stage 3: How to write the roles for sending.

#### Method 1: Discord to file
1. User types out the entire message into the Bot Channel. User begins with start;, ends with end; using shift-enter to act as a line break. 
2. User sends the message to the channel by pressing the enter key or send button. 
3. user types /roles with arg: write and arg: channel ID of destination and arg: MessageID of the message they just sent, then hit enter. 
4. Bot will read the message, will add the ch-id; of the destination channel to the correct spot, and will change the start; flag to write; to identify that the entry needs to be written to the file. 
5. Bot will push an ephemeral message to the user in-line to say that the write operation is complete. 
6. User can either type /sendroles to immediately mirror the role message out to the destination channel and the bot will delete the one the user sent into the bot channel earlier, or they can do /role arg: send and the bot will do the same action. 
7. Bot will change the write; flag to skip; and will capture the msg-id; placing it below ch-id; in the message after sending the message to the destined channel.
8. Bot will note the ID's of any reactions or buttons with reactid; and bttnid;, once per line after the data; flag.
9. Bot will call the commander, who will then write the data to roles.xlsx where column 1 is the date, column 2 is the channel ID, column 3 is the Message ID, column 4 through 10 is the button ID's and 11 through 21 is the reaction ID. 

The hope is that this data can be used later if the bot has to be restarted to re-link specific messages to button actions. 