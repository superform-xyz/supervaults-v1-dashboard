from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

class Morpho:
    def __init__(self):
        self.url = 'https://blue-api.morpho.org/graphql'
        self.client = Client(
            transport=RequestsHTTPTransport(url=self.url),
            fetch_schema_from_transport=True
        )


    def get_vault(self, vault_address):
        address_query = """
        {
            vaults(where: { address_in: ["%s"] }) {
            items {
                id
                address
            }
            }
        }
        """ % vault_address
            
        result = self.client.execute(gql(address_query))
        vaults = result.get('vaults', {}).get('items', [])
        if not vaults:
            return None
            
        vault_identifier = vaults[0]['id']
        
        # Now get the vault details using the ID
        vault_query = """
        {
          vault(id: "%s") {
            address
            state {
              allocation {
                market {
                  collateralAsset {
                    name
                    logoURI
                    symbol
                  }
                  state {
                    supplyApy
                    rewards {
                      supplyApr
                    }
                    utilization
                    liquidityAssets
                  }
                  lltv
                }
                supplyAssets
              }
            }
          }
        }
        """ % vault_identifier
        
        return self.client.execute(gql(vault_query)).get('vault')