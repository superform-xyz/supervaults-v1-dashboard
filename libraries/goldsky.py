from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
import json

class Goldsky:
    def __init__(self, chain_id):
        self.url = f'https://api.goldsky.com/api/public/project_cl94kmyjc05xp0ixtdmoahbtu/subgraphs/superform-v1-{chain_id}/1.1.8/gn'
        self.client = Client(
            transport=RequestsHTTPTransport(url=self.url),
            fetch_schema_from_transport=True
        )

    def get_superforms(self, superform_ids):
        string_ids = [str(id) for id in superform_ids]
        
        query = """
        {
          superforms(where: {superformID_in: %s}) {
            superformID
            superformAddress
            vaultAddress
            vaultDetails {
              name
              symbol
              decimals
              vaultAsset {
                address
                name
                decimals               
              }
            }
          }
        }
        """ % json.dumps(string_ids)  # Now passing string IDs
        
        return self.client.execute(gql(query)).get('superforms', [])