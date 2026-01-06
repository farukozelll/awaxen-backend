#!/usr/bin/env python3
"""
Generate a new Fernet encryption key for ENCRYPTION_KEY env variable.
"""
from cryptography.fernet import Fernet

key = Fernet.generate_key().decode()
print(f"\n🔐 New Encryption Key Generated:\n")
print(f"ENCRYPTION_KEY={key}")
print(f"\n📝 Add this to your .env file\n")
