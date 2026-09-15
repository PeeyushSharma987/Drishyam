from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Generate a 256-bit (32-byte) key
key = AESGCM.generate_key(bit_length=256)

with open("master.key", "wb") as key_file:
    key_file.write(key)
    
print("AES-256 Master Key generated and saved as 'master.key'!")
print("Keep this file safe. If you lose it, your photos are gone forever.")