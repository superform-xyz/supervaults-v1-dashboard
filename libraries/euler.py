from web3 import Web3
from typing import Optional, Dict, Any, List
import json
import os
from dotenv import load_dotenv

class Euler:
    # Lens addresses for different networks
    LENS_ADDRESSES = {
        1: '0x5c5E9d8C89C9E2Cb8E6e9a2Ae5bD8e39B432f49b',  # Mainnet
        8453: '0xc20B6e1d52ce377a450512958EEE8142063436CD'  # Base
    }

    def __init__(self, chain_id: int):
        """
        Initialize Euler client for a specific network
        
        Args:
            chain_id: The chain ID (1 for Ethereum mainnet, 8453 for Base)
        """
        # Load environment variables
        load_dotenv('.env.local')
        
        # Validate chain_id
        if chain_id not in self.LENS_ADDRESSES:
            raise ValueError(f"Unsupported chain_id: {chain_id}. Supported chains: {list(self.LENS_ADDRESSES.keys())}")

        # Get appropriate RPC URL based on chain_id
        rpc_url = None
        if chain_id == 1:
            rpc_url = os.getenv('ETHEREUM_RPC_URL')
        elif chain_id == 8453:
            rpc_url = os.getenv('BASE_RPC_URL')
            
        if not rpc_url:
            raise ValueError(f"No RPC URL configured for chain_id {chain_id}")
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Get lens address for the specified network
        self.lens_address = self.LENS_ADDRESSES[chain_id]
        
        # Load ABI from file
        with open("abi/euler_lens.json") as file:
            self.lens_abi = json.load(file)
        
        self.lens_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.lens_address),
            abi=self.lens_abi
        )

    def get_vault(self, vault_address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about an Euler vault using the VaultLens contract.
        
        Args:
            vault_address: The address of the vault to query
            
        Returns:
            Dictionary containing vault information or None if the vault doesn't exist
        """
        try:
            vault_info = self.lens_contract.functions.getVaultInfoFull(
                self.w3.to_checksum_address(vault_address)
            ).call()
            
            # Convert values to human-readable format using decimals
            decimals = vault_info[4]  # vaultDecimals
            
            return {
                'timestamp': vault_info[0],
                'address': vault_info[1],
                'name': vault_info[2],
                'symbol': vault_info[3],
                'decimals': decimals,
                'asset': {
                    'address': vault_info[5],
                    'name': vault_info[6],
                    'symbol': vault_info[7],
                    'decimals': vault_info[8]
                },
                'totalShares': float(vault_info[9]) / (10 ** decimals),
                'totalCash': float(vault_info[10]) / (10 ** decimals),
                'totalBorrowed': float(vault_info[11]) / (10 ** decimals),
                'totalAssets': float(vault_info[12]) / (10 ** decimals)
            }
            
        except Exception as e:
            print(f"Error fetching vault info: {e}")
            return None

    def get_vault_ltv(self, vault_address: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get LTV information for recognized collaterals of an Euler vault.
        Includes token names for each collateral.
        """
        with open("abi/erc20.json") as file:
            erc20_abi = json.load(file)

        ltv_info = self.lens_contract.functions.getRecognizedCollateralsLTVInfo(
            self.w3.to_checksum_address(vault_address)
        ).call()
            
        result = []
        for info in ltv_info:
            # Create ERC20 contract instance for the collateral
            collateral_address = info[0]
            token_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(collateral_address),
                abi=erc20_abi
            )
                
            # Get token name
            try:
                token_name = token_contract.functions.name().call()
            except Exception as e:
                print(f"Error fetching token name for {collateral_address}: {e}")
                token_name = collateral_address  # Fallback to address if name fetch fails
            print(token_name)
            result.append({
                'collateral': collateral_address,
                'collateralName': token_name,
                'borrowLTV': info[1] / 100,  # Convert basis points to percentage
                'liquidationLTV': info[2] / 100,
                'initialLiquidationLTV': info[3] / 100,
                'targetTimestamp': info[4],
                'rampDuration': info[5]
            })
            print(result)
            
        return result
        # try:
        #     # Load ERC20 ABI
        #     with open("abi/erc20.json") as file:
        #         erc20_abi = json.load(file)

        #     ltv_info = self.lens_contract.functions.getRecognizedCollateralsLTVInfo(
        #         self.w3.to_checksum_address(vault_address)
        #     ).call()
            
        #     result = []
        #     for info in ltv_info:
        #         # Create ERC20 contract instance for the collateral
        #         collateral_address = info[0]
        #         token_contract = self.w3.eth.contract(
        #             address=self.w3.to_checksum_address(collateral_address),
        #             abi=erc20_abi
        #         )
                
        #         # Get token name
        #         try:
        #             token_name = token_contract.functions.name().call()
        #         except Exception as e:
        #             print(f"Error fetching token name for {collateral_address}: {e}")
        #             token_name = collateral_address  # Fallback to address if name fetch fails
                
        #         result.append({
        #             'collateral': collateral_address,
        #             'collateralName': token_name,
        #             'borrowLTV': info[1] / 100,  # Convert basis points to percentage
        #             'liquidationLTV': info[2] / 100,
        #             'initialLiquidationLTV': info[3] / 100,
        #             'targetTimestamp': info[4],
        #             'rampDuration': info[5]
        #         })
            
        #     return result
            
        # except Exception as e:
        #     print(f"Error fetching vault LTV info: {e}")
        #     return None
