"""
OFAC (Office of Foreign Assets Control) compliance manager.

This service manages sanctions list checking to ensure compliance with
financial regulations and prevent sanctioned addresses from using the application.
"""
import logging
import os
import csv
import asyncio
import httpx
from typing import Set, Dict, Optional, List
from datetime import datetime, timedelta
from utils.web3_connection import w3
from web3.types import ChecksumAddress
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class OFACManager:
    """Service for managing OFAC sanctions list compliance."""
    
    # OFAC data source
    OFAC_LIST_URL = "https://raw.githubusercontent.com/ultrasoundmoney/ofac-ethereum-addresses/main/data.csv"
    
    def __init__(self) -> None:
        """Initialize the OFAC Manager."""
        self.sanctioned_addresses: Set[ChecksumAddress] = set()
        self.last_update: Optional[datetime] = None
        self.update_interval_hours = int(os.getenv('OFAC_UPDATE_INTERVAL_HOURS', '24'))
        self.compliance_enabled = os.getenv('OFAC_COMPLIANCE_ENABLED', 'true').lower() == 'true'
        
        if self.compliance_enabled:
            logger.info("OFAC compliance is ENABLED")
        else:
            logger.warning("OFAC compliance is DISABLED - only use for testing!")

    async def _fetch_ofac_list(self) -> Set[ChecksumAddress]:
        """Fetch the latest OFAC sanctions list from GitHub.
        
        Returns:
            Set[ChecksumAddress]: Set of sanctioned Ethereum addresses
        """
        sanctioned_addresses: Set[ChecksumAddress] = set()
        
        try:
            logger.info(f"Fetching OFAC sanctions list from {self.OFAC_LIST_URL}")
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(self.OFAC_LIST_URL)
                response.raise_for_status()
                
                # Parse CSV data
                csv_content = response.text
                csv_reader = csv.DictReader(csv_content.splitlines())
                
                for row in csv_reader:
                    # The CSV should have an 'address' column
                    address = row.get('address', '').strip()
                    if address:
                        try:
                            # Convert to checksum address
                            checksum_address = w3.to_checksum_address(address)
                            sanctioned_addresses.add(checksum_address)
                        except Exception as e:
                            logger.warning(f"Invalid address in OFAC list: {address} - {str(e)}")
                            continue
                            
            logger.info(f"Successfully loaded {len(sanctioned_addresses)} sanctioned addresses")
            return sanctioned_addresses
            
        except Exception as e:
            logger.error(f"Failed to fetch OFAC sanctions list: {str(e)}")
            # Return empty set on error - better to allow transactions than crash
            return set()

    async def update_sanctions_list(self) -> bool:
        """Update the sanctions list if needed.
        
        Returns:
            bool: True if update was successful or not needed, False if failed
        """
        if not self.compliance_enabled:
            return True
            
        now = datetime.now()
        
        # Check if update is needed
        if (self.last_update is None or 
            now - self.last_update > timedelta(hours=self.update_interval_hours)):
            
            logger.info("Updating OFAC sanctions list")
            new_addresses = await self._fetch_ofac_list()
            
            if new_addresses:  # Only update if we got valid data
                self.sanctioned_addresses = new_addresses
                self.last_update = now
                logger.info(f"OFAC sanctions list updated with {len(self.sanctioned_addresses)} addresses")
                return True
            else:
                logger.error("Failed to update OFAC sanctions list - keeping existing data")
                return False
        
        return True  # No update needed

    async def is_address_sanctioned(self, address: str) -> bool:
        """Check if an address is on the OFAC sanctions list.
        
        Args:
            address: Ethereum address to check
            
        Returns:
            bool: True if address is sanctioned, False otherwise
        """
        if not self.compliance_enabled:
            return False
            
        try:
            # Ensure sanctions list is up to date
            await self.update_sanctions_list()
            
            # Convert to checksum address
            checksum_address = w3.to_checksum_address(address)
            
            is_sanctioned = checksum_address in self.sanctioned_addresses
            
            if is_sanctioned:
                logger.warning(f"BLOCKED: Sanctioned address detected: {checksum_address}")
            
            return is_sanctioned
            
        except Exception as e:
            logger.error(f"Error checking OFAC sanctions for address {address}: {str(e)}")
            # On error, default to not sanctioned to avoid blocking legitimate users
            return False

    async def check_transaction_compliance(self, from_address: str, to_address: str, 
                                         user_id: Optional[str] = None) -> Dict[str, bool]:
        """Check if a transaction involves any sanctioned addresses.
        
        Args:
            from_address: Sender address
            to_address: Recipient address  
            user_id: Optional user ID for logging
            
        Returns:
            Dict with compliance check results
        """
        if not self.compliance_enabled:
            return {
                'is_compliant': True,
                'from_sanctioned': False,
                'to_sanctioned': False,
                'blocked_reason': None
            }
        
        from_sanctioned = await self.is_address_sanctioned(from_address)
        to_sanctioned = await self.is_address_sanctioned(to_address)
        
        is_compliant = not (from_sanctioned or to_sanctioned)
        blocked_reason = None
        
        if not is_compliant:
            reasons = []
            if from_sanctioned:
                reasons.append("sender address is sanctioned")
            if to_sanctioned:
                reasons.append("recipient address is sanctioned")
            blocked_reason = " and ".join(reasons)
            
            # Log the blocked transaction attempt
            user_hash = hash_user_id(user_id) if user_id else "unknown"
            logger.critical(
                f"COMPLIANCE VIOLATION: Transaction blocked for user {user_hash}. "
                f"From: {from_address} (sanctioned: {from_sanctioned}), "
                f"To: {to_address} (sanctioned: {to_sanctioned}). "
                f"Reason: {blocked_reason}"
            )
        
        return {
            'is_compliant': is_compliant,
            'from_sanctioned': from_sanctioned,
            'to_sanctioned': to_sanctioned,
            'blocked_reason': blocked_reason
        }

    async def check_wallet_compliance(self, address: str, user_id: Optional[str] = None) -> bool:
        """Check if a wallet address is compliant for use.
        
        Args:
            address: Wallet address to check
            user_id: Optional user ID for logging
            
        Returns:
            bool: True if compliant, False if sanctioned
        """
        if not self.compliance_enabled:
            return True
            
        is_sanctioned = await self.is_address_sanctioned(address)
        
        if is_sanctioned:
            user_hash = hash_user_id(user_id) if user_id else "unknown"
            logger.critical(
                f"COMPLIANCE VIOLATION: Sanctioned wallet access attempt by user {user_hash}. "
                f"Address: {address}"
            )
        
        return not is_sanctioned

    def get_compliance_status(self) -> Dict[str, any]:
        """Get current compliance system status.
        
        Returns:
            Dict with compliance system information
        """
        return {
            'compliance_enabled': self.compliance_enabled,
            'sanctioned_addresses_count': len(self.sanctioned_addresses),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'update_interval_hours': self.update_interval_hours,
            'next_update_due': (
                (self.last_update + timedelta(hours=self.update_interval_hours)).isoformat()
                if self.last_update else "immediate"
            )
        }

# Create singleton instance
ofac_manager: OFACManager = OFACManager()