from web3.auto import w3
import os

# Define the base directory path
base_dir = "blockchain/dlt-network-docker/dlt-node/"  # Path adjusted for root execution

# Define the password to decrypt the keystore files
password = "netcom;"

# Function to decrypt and print private keys from a keystore file
def decrypt_and_print_private_key(keyfile_path):
    with open(keyfile_path) as keyfile:
        encrypted_key = keyfile.read()
        private_key = w3.eth.account.decrypt(encrypted_key, password)

    import binascii
    return binascii.b2a_hex(private_key)

# Find and decrypt private keys in all keystore directories
for root, dirs, files in os.walk(base_dir):
    for dir in dirs:
        if dir.startswith("node") and os.path.exists(os.path.join(root, dir, "keystore")):
            keystore_dir = os.path.join(root, dir, "keystore")
            print(f"Private Keys for {dir}:")
            for filename in os.listdir(keystore_dir):
                if filename.startswith("UTC--"):
                    keyfile_path = os.path.join(keystore_dir, filename)
                    private_key_hex = decrypt_and_print_private_key(keyfile_path)
                    print(f"Account in {filename}: {private_key_hex.decode('utf-8')}")