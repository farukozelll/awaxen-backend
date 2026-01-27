#!/usr/bin/env python3
"""
Generate a new Fernet encryption key for ENCRYPTION_KEY env variable.
"""
from cryptography.fernet import Fernet

key = Fernet.generate_key().decode()
