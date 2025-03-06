from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message with instructions on how to use the bot in private messages."""
    user = update.effective_user
    bot_username = context.bot.username
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! Here's how to use this bot:\n\n"
        f"⚠️ <b>Important</b>: For security reasons, this bot only works in private messages.\n\n"
        f"To send a private message:\n"
        f"1. Click on my username: @{bot_username}\n"
        f"2. Press the 'Start' button\n"
        f"3. You can now send me commands privately\n\n"
        f"<b>Available Commands</b>:\n"
        f"• /start - Display the welcome message\n"
        f"• /wallet - Create or view your wallet\n"
        f"• /balance - Check your token balances\n"
        f"• /send - Send BNB or tokens\n"
        f"• /receive - Get your wallet address\n"
        f"• /backup - Backup your private key\n"
        f"• /recover - Restore a wallet from a private key\n"
        f"• /help - Show this help message"
    )

async def group_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message specifically for group chats."""
    user = update.effective_user
    bot_username = context.bot.username
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm the TidalDex Wallet Bot.\n\n"
        f"⚠️ <b>Important</b>: For security reasons, I only work in private messages.\n\n"
        f"To send me a private message:\n"
        f"1. Click on my username: @{bot_username}\n"
        f"2. Press the 'Start' button\n"
        f"3. You can now send me commands privately\n\n"
        f"Try <code>/help</code> in our private chat for a list of all available commands."
    )

async def universal_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help command in both private and group chats."""
    # Check if command format includes bot username (common in groups)
    if hasattr(update, 'message') and update.message and update.message.text:
        command_text = update.message.text
        if '@' in command_text:
            parts = command_text.split('@')
            if len(parts) > 1 and parts[1] != context.bot.username:
                return
    
    # Check chat type and call appropriate handler
    if update.effective_chat.type == 'private':
        await help_command(update, context)
    else:
        await group_help_command(update, context) 