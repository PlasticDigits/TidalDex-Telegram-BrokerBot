#!/usr/bin/env python3
"""
Migration script for encrypting wallet addresses.

This script migrates existing plain-text wallet addresses to encrypted format
to improve security. It should be run once after updating the codebase with
address encryption functionality.

Usage:
    python migrate_addresses.py [--dry-run] [--user-id USER_ID]

Arguments:
    --dry-run: Show what would be migrated without making changes
    --user-id: Migrate only a specific user's wallets
"""

import argparse
import logging
import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.utils import migrate_wallet_addresses, migrate_user_wallet_addresses
from db.connection import test_connection, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Migrate wallet addresses to encrypted format')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be migrated without making changes')
    parser.add_argument('--user-id', type=str,
                       help='Migrate only a specific user\'s wallets (provide the original user ID)')
    
    args = parser.parse_args()
    
    logger.info("Starting wallet address migration...")
    
    # Test database connection
    if not test_connection():
        logger.error("Database connection failed. Please check your database configuration.")
        sys.exit(1)
    
    # Initialize database if needed
    if not init_db():
        logger.error("Database initialization failed.")
        sys.exit(1)
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made to the database")
        # For dry run, we would need to implement a version that doesn't update the database
        logger.warning("Dry run mode not yet implemented. Please run without --dry-run to perform actual migration.")
        return
    
    try:
        if args.user_id:
            # Migrate specific user
            logger.info(f"Migrating addresses for user: {args.user_id}")
            # Note: For user-specific migration, we would typically need the user's PIN
            # This should be handled through the application interface when the user logs in
            success, message = migrate_user_wallet_addresses(args.user_id, None)
            
            if success:
                logger.info(f"User migration completed successfully: {message}")
            else:
                logger.error(f"User migration failed: {message}")
                sys.exit(1)
        else:
            # Migrate all wallets
            logger.info("Migrating all wallet addresses...")
            success, message = migrate_wallet_addresses()
            
            if success:
                logger.info(f"Migration completed successfully: {message}")
            else:
                logger.error(f"Migration failed: {message}")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"Migration failed with unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    
    logger.info("Migration completed successfully!")

if __name__ == "__main__":
    main() 