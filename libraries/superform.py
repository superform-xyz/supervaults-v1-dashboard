import json
import os
import requests
import pandas as pd
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# Load environment variables from .env.local file
load_dotenv(".env.local")

class SuperformConfig:
    def __init__(self, chain_id):
        self.chain_id = chain_id
        self.chain_ids = [1,10,56,137,250,8453,42161,43114,81457,59144]
        self.chain_colors = {
            1: 'gray',
            10: 'red',
            56: 'yellow',
            137: 'purple',
            250: 'lightblue',
            8453: 'blue',
            42161: 'navy',
            43114: 'maroon',
            81457: 'gold',
            59144: 'black'
        }

        self._configure_chain()

    def _configure_chain(self):
        # Simplified chain configs with just name and base URL
        chain_configs = {
            42161: ('Arbitrum', 'https://arb1.arbitrum.io/rpc'),
            43114: ('Avalanche', 'https://api.avax.network/ext/bc/C/rpc'),
            56: ('BSC', 'https://bsc-dataseed.binance.org'),
            1: ('Ethereum', 'https://eth.llamarpc.com'),
            10: ('Optimism', 'https://mainnet.optimism.io'),
            137: ('Polygon', 'https://polygon-rpc.com'),
            8453: ('Base', 'https://mainnet.base.org'),
            250: ('Fantom', 'https://rpc.ftm.tools'),
            81457: ('Blast', 'https://blast.blockpi.network/v1/rpc/public'),
            59144: ('Linea', 'https://rpc.linea.build')
        }

        if self.chain_id in chain_configs:
            self.chain_name, self.rpc = chain_configs[self.chain_id]
            self.w3 = Web3(Web3.HTTPProvider(self.rpc))
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            self.timeout = 90 if self.chain_id == 10 else (30 if self.chain_id == 1 else 15)

            # Load contract addresses and ABI's
            with open("deployments/addresses.json") as file:
                self.deployments = json.load(file)[str(self.chain_id)]
            with open("abi/erc20.json") as file:
                self.erc20_abi = json.load(file)
            with open("abi/erc4626.json") as file:
                self.erc4626_abi = json.load(file)
            with open("abi/erc4626_form.json") as file:
                self.erc4626_form_abi = json.load(file)
            with open("abi/supervault.json") as file:
                self.supervault_abi = json.load(file)
        else:
            raise Exception("not a valid chain_id")

class SuperVault:
    """
    Read values from SuperVault
    """
    def __init__(self, chain_id, vault_address):
        self.config = SuperformConfig(chain_id)
        self.vault_address = vault_address
        with open("abi/supervault.json") as file:
            self.supervault_abi = json.load(file)
        self.supervault = self.config.w3.eth.contract(
            address=vault_address,
            abi=self.supervault_abi
        )

    def get_whitelisted_vaults(self):
        vaults = self.supervault.functions.getWhitelist().call()
        return vaults
    
    def get_supervault_data(self):
        data = self.supervault.functions.getSuperVaultData().call()
        return data
    
class SuperformAPI:
    def __init__(self):
        self.url = 'https://api.superform.xyz/'
        self.api_key = os.getenv('SUPERFORM_API_KEY')

    def _request(self, action):
        url = self.url + action
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'SF-API-KEY': self.api_key
        }
        response = requests.get(url, headers=headers)
        result = json.loads(response.text)
        return result

    def get_vaults(self):
        action = f'vaults'
        response = self._request(action)
        return response

    def get_supervaults(self):
        action = f'stats/vault/supervaults'
        response = self._request(action)
        return response
    
    def get_vault_data(self, superform_id):
        action = f'vault/{superform_id}'
        response = self._request(action)
        return response
