# Bot Planfile for syntax, and full rebuild for correct operation. 

## Stage 1: The Initial Build

1. Create the flags and instructions for the bot to function as desired. These instructions should be clear and concise, and they should be useful for the individual programming the bot. 
2. Split the core functions of the bot into multiple components, the fetch, commander, verifier and ranker pieces as separate .py scripts will all communicate with each other. However, they will all act separately and like individuals using the BotInterface script that will take slash commands, translate them into what script is used and what args are used, before passing it back to the interface for the return to Discord. 
3. We use roles.txt for the /sendmessage command and the /sendroles command. 
4. We use a .xlsx spreadsheet for the /Verify command so that when a user intends to verify they are from Star Cotizen, we can retain the Star Citizen username, the randomised code issued to them and their Discord Username. This way we will be able to identify a player even if their Discord Username differs from their RSI Profile. For GDPR purposes, this is the only information we are allowed to store and the .xlsx file will be added to .gitignore.
5. Redesign the entire Regex flags and matching system to be easier to use and faster to type, without getting repetitive and create a small .exe program that will enable the super speedy creation of a roles.txt file. 


## Stage 2: The .txt file flags
### User Flags

* start;
	* The natural start of the block.
* note-start; Note goes here, including line breaks.
    * user can leave a note about what the channel ID is refering to, or what theyre hoping to achieve from the layout.
* note-end;
    * This flag is used to denote the ending of a note. 
* msg-start;
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
* give-role-btn-x; role name
    * ties to btn-x with the argument: role name. 
    * Example is give-role-btn-1; Happy Person
    * The user who interracted with the button will receive the role tied to it.
* take-role-btn-x; role name
    * ties to button x with the argument: role name.
    * Example is take-role-btn-1; Happy Person
    * This will remove the 'Happy Person' role when the button is pressed.
* toggle-role-btn-x; role name
    * ties to btn-x with the argument: role name
    * Example is toggle-role-btn-1; Strange Person
    * The user who clicks it will be receiving the role on the first click, lose the role on the next, and all subsequent clicks will alternate between gaining and loosing the named role
* give-react-x; role name
    * ties to react-x with argument; role name
    * Example is give-react-1; Sad Person
    * This will only give the names role to the user who selects the reaction. 
* take-react-x; role name
    * ties to react-x with argument: role name
    * Example is take-react-1; Sad Person
    * User who selects this reaction will lose the named role. 
* toggle-react-x; role name
    * ties to react-x with argument: role name
    * Example is toggle-react-1; StRaNgE PeRsOn
    * User who clicks this reaction can freely take or lose the role tied to the reaction.
* data;
	* User enters the data; flag, this tells the /sendroles command where it can stash data relating to buttons and reaction roles, in the event that the bot has to be restarted.
* end;
	* User places the end flag at the bottom of their block. This signals that they are done with this block.
	* User leaves a blank line after this, then goes back to the top of the list with the start; flag.

### Bot Only Flags
* write.
    * When the user uses the /roles arg: write arg: channel-ID arg: invoking-channel-message-id the bot will copy the entire message from start; to end; into a free line in roles.txt then will delete the message that is tied to the in-channel-message-id that it copied. 
    * It will write the ch-id.xxxxxxxx below the data; flag
    * it will write the msg-id.xxxxxxx of the message it sent below the ch-id. flag
    * it will add each react-id-x.xxxxxxx:"role name" one per line (even if react-id's are numbered the same but have different role names attached, this is fine)
    * it will add btn-id-x.xxxxxxxxx:"role name" one per line (even if btn-id's are numbered the same but have different role names attached, this is fine)
* NOTE
    * ch-id.xxxxxxxxxxx
    	* Used to identify what channel a message is going into. The bot should automatically identify this flag and append > and prepend <# so it can accurately identify the channel ID.
    * msg-id.xxxxxxxxxxx
    	* Identifier for any pre-existing message made by the bot.
    * react-id-x.xxxxxxxxxxx:"role name"
    	* The -x refers to a specific reaction identifier that's been posted by the /sendroles command.
    * btn-id-x.xxxxxxxxx
    	* The -x refers to the specific button identifier of a message posted by the /sendroles command.
* sent. 
    * When the user types /roles arg: send the bot will send all roles.txt entries who opens with write., once sent, the write. flag will be removed and replaced with the sent. flag. 
    * Bot will query Commander to grab data regarding the buttons and reactions by ID and will then enter the roles.xlsx
        * Column 1 Channel ID
        * Column 2: Message ID
        * Column 3: Reaction ID
        * Column 4: Role Name
        * Column 5: Button ID
        * Column 6: Role Name
        * Column 7: Date of entry
        * Column 8: Channel Name of Entry
    * The Commander will fill each row with the same data from Columns 1 and 2 if the columns 3 though 6 contain disimilar data from the previous row oof the same timestamp (as in Column 1)
    * The Commander will fill columns 7 and 8 at the first row of data only where the channel-id and message-id match. 
* skip.
    * The commander will change the sent. flag to skip. which will tell all bots (except the initiator script) to ignore everything up to the next start; flag.
    * the Initiator will check all skip. flags, will check the ch-id. and msg-id. flags from the data; , it will check the roles.xlsx in column 2 and 3 to match both to get the btn-id-x. and the react-id-x. numbers from the .txt, and will pass this to the roles.py script to allow for the buttons to work again.

## Stage 3: The Verifier
NOTE: There will be no human interraction for this piece, this is purely end user/bot interraction.
1. User pops into the server! They select the Accept Rules button int he rules page, they do the usual stuff. however, in order to enter the Syndicate proper, they must be in the Org on the RSI website, otherwise, they will not be entitled to receive the role that will allow them entry to the syndicate itself.
2. User gets an invite to join our inner sanctum. 
3. User types /Verify arg: RSI Username arg: [leave blank] into any chat channel they have access to. 
4. Bot will go to https://robertsspaceindustries.com/citizens/Users_RSI_Username and scrape the page. if the <strong class="value data10">SPBOYS</strong> is found this is suitable. however, if <div class="member-visibility-restriction member-visibility-r trans-03s"> == $0 and below if <div class="restriction-r restriction"></div> is found, then notify the bot channel immediately. 
5. If pass, assign the Verified role. If not:
6. Present the user with a 6 digit code and instructions to copy the code to their RSI Short Bio and save the bio, accessible at https://robertsspaceindustries.com/en/account/profile, then to return and run /verify arg: RSI Username arg: xxxxxx (the code). Write to verification.xlsx 
    * Column 1: Discord Username
    * Column 2: RSI Org Fail
    * Column 3: xxxxxx (the code)
    * Column 4: RSI Username
    * Column 5: Verified/Not Verified
    * Column 6: Who Forced it (The User-ID <@xxxxxxxxx>)
    * Column 7: Who Forced it (The username)
7. User returns and types /verify rsi_username xxxxxx and hits enter, bot will then go to https://robertsspaceindustries.com/citizens/rsi_username and checks the short bio or signature field for the code provided by the user. if the code matches, the bot will give the Verified role and fill verified into Column 5. The bot will then inform the user that verification is complete, and they can now delete the code from their profile. The bot will never use the same verification code with another user, ever. 
8. If the user does not return within 24 hours to complete verification, the bot will mark column 5 Not Verified, retain the code, and will notify the bot channel. 
9. Admin only may use /verify arg: unlock arg: Discord Username to unblock the blocked verification, which will delete the entire row where the discord username is found, releasing the 6 digit code for the blocked user to re-verify. Admins may use the /verify command with the unlock argument as often as they want to assist a user. 
10. Admin may use the /verify arg: force arg: discord username arg: RSI_Username arg: True/False to force a manual verification. This will issue a 6 digit code directly to the spreadsheet and enter "FORCED" into Column 2 and the Discord User-ID <@xxxxxxxxxxxxx> of who forced it into Column 6 and their Discord_Username @MR_SHINY_KITTEN <---- (Thats an example!) in Column 7. 