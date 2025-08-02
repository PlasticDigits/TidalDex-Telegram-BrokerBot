"""
Admin command to check OFAC compliance system status.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from typing import Optional
from db.utils import hash_user_id

# Import OFAC compliance manager
try:
    from services.compliance import ofac_manager
    OFAC_AVAILABLE = True
except ImportError:
    OFAC_AVAILABLE = False
    ofac_manager = None

logger = logging.getLogger(__name__)

async def compliance_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show OFAC compliance system status (admin only).
    """
    user = update.effective_user
    if not user:
        return
    
    # Simple admin check - you can modify this to use your admin system
    # For now, just log the request
    logger.info(f"Compliance status requested by user {hash_user_id(user.id)}")
    
    if not OFAC_AVAILABLE or not ofac_manager:
        await update.message.reply_text(
            "⚠️ OFAC Compliance System: NOT AVAILABLE\n\n"
            "The compliance module is not installed or configured."
        )
        return
    
    try:
        status = ofac_manager.get_compliance_status()
        
        status_text = (
            f"🛡️ **OFAC Compliance Status**\n\n"
            f"🔧 **System Status:**\n"
            f"• Enabled: {'✅ YES' if status['compliance_enabled'] else '❌ DISABLED'}\n"
            f"• Sanctioned Addresses: {status['sanctioned_addresses_count']:,}\n\n"
            f"📅 **Update Schedule:**\n"
            f"• Last Update: {status['last_update'] or 'Never'}\n"
            f"• Update Interval: {status['update_interval_hours']} hours\n"
            f"• Next Update Due: {status['next_update_due']}\n\n"
            f"🔍 **Data Source:**\n"
            f"• GitHub: ultrasoundmoney/ofac-ethereum-addresses\n"
            f"• Format: CSV (Ethereum addresses)\n\n"
            f"⚖️ **Compliance Coverage:**\n"
            f"• ✅ Wallet Creation\n"
            f"• ✅ Wallet Import\n"
            f"• ✅ Send Transactions\n"
            f"• ✅ Compliance Logging"
        )
        
        if not status['compliance_enabled']:
            status_text += "\n\n⚠️ **WARNING:** OFAC compliance is DISABLED!"
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error getting compliance status: {str(e)}")
        await update.message.reply_text(
            "❌ Error retrieving compliance status. Check logs for details."
        )

# Create command handler
compliance_status_handler = CommandHandler("compliance_status", compliance_status_command)