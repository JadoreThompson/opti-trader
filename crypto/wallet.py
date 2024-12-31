import secrets
import os

from dotenv import load_dotenv
from ecdsa import SECP256k1, SigningKey
from Crypto.Hash import keccak
from web3 import Web3

# Local
from exceptions import (
    Web3ConnectionError,
    InvalidAction
)


load_dotenv()

class CryptoWallet:
    def __init__(self, network: str='mainnet'):
        self._raw_private_key = secrets.token_bytes(32)
        self._public_key = self._gen_public_key()
        self._address = self._gen_address()
        
        if network not in ['mainnet', 'sepolia']:
            raise InvalidAction("Network must be mainnet or testnet")
        
        self._network = network
        self._w3 = Web3(Web3.HTTPProvider(f"https://{self._network}.infura.io/v3/{os.getenv('MM_API_KEY')}"))
        
    def _gen_public_key(self):
        return \
            SigningKey.from_string(
                self._raw_private_key, 
                curve=SECP256k1
            )\
            .get_verifying_key()\
            .to_string()
        
    def _gen_address(self):
        khash = keccak.new(digest_bits=256)
        khash.update(self._public_key) 
        return khash.digest()[-20:]
    
    def send_transaction(self, recipient: str, amount: float) -> None:
        if not self._w3.is_connected():
            raise Web3ConnectionError('Connection to {} absent'.format(self._network))
        
        txn = {
            'nonce': self._w3.eth.get_transaction_count(Web3.to_checksum_address(self.address.lower())),
            'to': Web3.to_checksum_address(recipient.lower()),
            'value': Web3.to_wei(amount, 'ether'),
            'gas': 21000,
            'gasPrice': self._w3.eth.gas_price,
            'chainId': self._w3.eth.chain_id,
        }
        
        if txn['value'] + (txn['gas'] * txn['gasPrice']) > self._w3.to_wei(self.get_balance(), 'ether'):
            raise ValueError('Insufficient Balance')
        
        
        signed_txn = self._w3.eth.account.sign_transaction(txn, private_key=self.private_key)
        return self._w3.eth.wait_for_transaction_receipt(
            self._w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        )
    
    def get_balance(self, address: str=None) -> float:
        target_address = self.address if address is None else address
        wei_balance = self._w3.eth.get_balance(Web3.to_checksum_address(target_address))
        return self._w3.from_wei(wei_balance, 'ether')
        
    @property
    def private_key(self) -> str:
        return f"0x{self._raw_private_key.hex()}"

    @property
    def public_key(self) -> str:
        return f"0x{self._public_key.hex()}"

    @property
    def address(self) -> str:
        return f"0x{self._address.hex()}"


if __name__ == "__main__":
    wallet = CryptoWallet()
    print(wallet._gen_address())