The roles-bot of the Cowboy's Messenger will read from roles.txt (currently located on drive D: on Fir3Fly's PC.) It will be moved into the GitHub Repo so it can pull directly from there. 

# How it works

### The Order of Functions
Skip. (This will be in place of Start. if the bot has handled it already and will skip this piece if the Skip. command is used)
Start. (always place at the start of a block)
CH-ID<#xxxxxxxxxxxxxx>CHANNEL_NAME (This always comes next)
MSG-ID:xxxxxxxxxxxx (If it applies, this goes next)
Replace_MSG (If you want to replace a message, this goes next)
MSG; (This comes next int he flow)
EMOTE_x; <":Emote:MESSAGE"> (Use for Reaction roles Only. This goes next. x is a number, place each emote on a new line)
MK-BTN_x; Colour=COLOUR; Emoji; Text (Makes a button (button x (X being a number) for a colour,, either red, green, blue or orange) with an optional emoji (leave out "emoji;" entirely to not require an emoji) then the text associated with the button)
Toggle-Role (this allows a role to be toggled by the user clicking multiple times.)
Static-Role (The user can only interract once to get the associated role, subsequent clicks by the user will be ignored)
Give_Role_x; "Role Name" (This is next)
End. (This goes last, this tells the bot to move to the next Start. identifier)


### EXAMPLE 1: Raw Start

Start.
CH-ID<#1404524405207339149>RULES
MSG;
1. Poaching players from the org is forbidden - Poaching will be met with extreme consequences.
2. Do not use foul language in text channels - Read the room in Voice Channels.
3. Leave the ego on the battlefield. Nobody is better than anyone else.
4. Don't harass new players - We were all new at some point. 
5. Keep NSFW content to the NSFW spaces.
6. Friendly Fire is not tolerated. unless you got caught in crossfire.
7. Griefing is not tollerated. Immediate dismissal will happen.
8. Be tollerant of other peoples background and origins.
9. Please use english where possible. Please contact Admin for a dedicated language-specific VC.
EMOTE_1; :White_Check_Mark: "Accept"
Give_Role_1; "Rules Accepted"
End.

### EXAMPLE 2: Existing Message Start

Start.
CH-ID<#1404524405207339149>RULES
MSG-ID:1409229575489065011
EMOTE_1; :White_Check_Mark: "Accept"
Give_Role_1; "Rules Accepted"
End.

### EXAMPLE 3: Replace Message Start

Start.
CH-ID<#1404524405207339149>RULES
MSG-ID:1409229575489065011
Replace_MSG
MSG;
1. Poaching players from the org is forbidden - Poaching will be met with extreme consequences.
2. Do not use foul language in text channels - Read the room in Voice Channels.
3. Leave the ego on the battlefield. Nobody is better than anyone else.
4. Don't harass new players - We were all new at some point. 
5. Keep NSFW content to the NSFW spaces.
6. Friendly Fire is not tolerated. unless you got caught in crossfire.
7. Griefing is not tollerated. Immediate dismissal will happen.
8. Be tollerant of other peoples background and origins.
9. Please use english where possible. Please contact Admin for a dedicated language-specific VC.
EMOTE_1; :White_Check_Mark: "Accept"
Give_Role_1; "Rules Accepted"
End.