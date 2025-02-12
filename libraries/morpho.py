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
        # Single query that gets both vault ID and details
        combined_query = """
        {
          vaults(where: { address_in: ["%s"] }) {
            items {
              id
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
        }
        """ % vault_address
            
        result = self.client.execute(gql(combined_query))
        vaults = result.get('vaults', {}).get('items', [])
        
        if not vaults:
            return None
            
        # Restructure the response to match the expected format
        vault_data = vaults[0]
        return {
            'address': vault_data['address'],
            'state': vault_data['state']
        }