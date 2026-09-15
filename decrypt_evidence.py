import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def decrypt_image(encrypted_filepath):
    try:
        # 1. Load your secret master key
        with open("master.key", "rb") as key_file:
            key = key_file.read()
            
        # 2. Read the locked evidence file
        with open(encrypted_filepath, "rb") as enc_file:
            file_data = enc_file.read()
            
        # 3. Separate the cryptographic salt (nonce) from the encrypted image
        # We used a 12-byte nonce during encryption
        nonce = file_data[:12]
        encrypted_data = file_data[12:]
        
        # 4. Decrypt the data
        aesgcm = AESGCM(key)
        decrypted_data = aesgcm.decrypt(nonce, encrypted_data, None)
        
        # 5. Save the unlocked image
        # Remove the '.aes' extension to get the original .jpg name
        original_filename = encrypted_filepath.replace(".aes", "") 
        
        with open(original_filename, "wb") as img_file:
            img_file.write(decrypted_data)
            
        print(f"✅ Success! Evidence decrypted and saved as: {original_filename}")
        
    except FileNotFoundError:
        print("❌ Error: Could not find the master key or the encrypted file.")
    except Exception as e:
        print(f"❌ Decryption failed! The file may be tampered with or the key is wrong. ({e})")

# Example usage: Replace this with the actual name of your encrypted file
target_file = "C:/Users/Peeyush Sharma/Documents/border_security_prototype/intrusions/threat_2026-09-11_09-58-54.jpg.aes" 
decrypt_image(target_file)


