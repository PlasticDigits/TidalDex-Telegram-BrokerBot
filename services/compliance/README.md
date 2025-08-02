# OFAC Compliance System

This module implements Office of Foreign Assets Control (OFAC) sanctions compliance for the TidalDex Telegram Bot.

## Overview

The OFAC compliance system automatically:
- ✅ **Fetches sanctions lists** from [OFAC Ethereum Addresses](https://github.com/ultrasoundmoney/ofac-ethereum-addresses)
- 🚫 **Blocks sanctioned wallets** during creation and import
- 🛡️ **Prevents transactions** to/from sanctioned addresses
- 📋 **Logs violations** for compliance reporting
- 🔄 **Auto-updates** sanctions list daily

## Features

### Wallet Protection
- **Creation**: Prevents creating wallets with sanctioned addresses
- **Import**: Blocks importing sanctioned private keys
- **Access**: Continuously monitors wallet compliance

### Transaction Protection  
- **Send Operations**: Checks both sender and recipient addresses
- **Real-time Blocking**: Immediate transaction blocking for sanctioned addresses
- **Clear Messaging**: User-friendly compliance violation messages

### Compliance Logging
- **Critical Logging**: All violations logged at CRITICAL level
- **User Privacy**: User IDs are hashed in logs
- **Audit Trail**: Complete compliance event tracking

## Configuration

Add to your `.env` file:

```bash
# Enable/disable OFAC compliance (true/false)
OFAC_COMPLIANCE_ENABLED=true

# Update interval in hours (default: 24)
OFAC_UPDATE_INTERVAL_HOURS=24
```

## Data Source

The system uses the community-maintained [OFAC Ethereum Addresses](https://github.com/ultrasoundmoney/ofac-ethereum-addresses) repository, which provides:
- ✅ Up-to-date sanctions data
- 🔍 Ethereum address focus
- 📄 CSV format for easy parsing
- 🤝 Community-verified accuracy

## Security & Privacy

- **Graceful Degradation**: System continues operating if OFAC service fails
- **Error Tolerance**: Failed compliance checks default to allowing operations
- **Privacy Protection**: User data is hashed in compliance logs
- **No Data Collection**: Only addresses are checked, no personal data stored

## Compliance Status

Check system status:
```python
from services.compliance import ofac_manager

status = ofac_manager.get_compliance_status()
print(f"Compliance enabled: {status['compliance_enabled']}")
print(f"Sanctioned addresses: {status['sanctioned_addresses_count']}")
print(f"Last update: {status['last_update']}")
```

## Legal Notice

This system is designed to help with OFAC compliance but does not guarantee complete legal compliance. Organizations should:
- ✅ Consult legal counsel for compliance requirements
- ✅ Implement additional compliance measures as needed
- ✅ Regularly review and update compliance procedures
- ✅ Monitor compliance logs and reporting

## Testing

For testing environments only, compliance can be disabled:
```bash
OFAC_COMPLIANCE_ENABLED=false
```

**⚠️ WARNING: Never disable OFAC compliance in production!**