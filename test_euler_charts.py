from dash import Dash, html
from libraries.euler import Euler
from main import create_euler_charts

# Test app
app = Dash(__name__)

# Mock vault ID
TEST_VAULT = "0x0a1a3b5f2041f33522c4efc754a7d096f880ee16"

def test_euler_charts():
    # Initialize Euler client for Base
    euler = Euler(8453)  # Base chain ID
    
    # Get vault LTV data
    vault_data = euler.get_vault_ltv(TEST_VAULT)
    
    if vault_data:
        # Create charts
        charts = create_euler_charts(vault_data)
        
        # Create simple layout to display charts
        app.layout = html.Div([
            html.H1("Euler LTV Charts Test"),
            charts if charts else html.Div("No charts generated")
        ])
        
        # Run the test app
        app.run_server(debug=True, port=8051)
    else:
        print("No vault data retrieved")

if __name__ == "__main__":
    test_euler_charts() 