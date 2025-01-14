import os
import json
from dash import Dash, html, dcc
import pandas as pd
from web3 import Web3
from functools import wraps
from libraries.superform import SuperVault, SuperformAPI, SuperformConfig
from libraries.morpho import Morpho
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import plotly.express as px
import random
import logging
import sys
import time 

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------

# Set higher logging level for noisy libraries
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('graphql').setLevel(logging.CRITICAL)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('dash').setLevel(logging.ERROR)  

# Configure our app logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Constants and Configurations
# -----------------------------------------------------------------------------

COMMON_GRAPH_CONFIG = {
    'displayModeBar': False,
    'responsive': True,
    'displaylogo': False,
    'modeBarButtonsToRemove': ['toImage'],
    'showAxisDragHandles': False,
    'showAxisRangeEntryBoxes': False,
    'showTips': False,
    'doubleClick': False,
    'scrollZoom': False,
}

CHART_FONT_FAMILY = "LabGrotesqueMono" 

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

def retry_with_backoff(retries=3, backoff_in_seconds=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        logger.error(f"Failed after {retries} attempts: {str(e)}")
                        raise
                    wait = (backoff_in_seconds * 2 ** x + 
                           random.uniform(0, 1))
                    logger.warning(f"Attempt {x + 1} failed, retrying in {wait:.2f}s: {str(e)}")
                    time.sleep(wait)
                    x += 1
        return wrapper
    return decorator

# -----------------------------------------------------------------------------
# UI Components - Basic
# -----------------------------------------------------------------------------

def create_header():
    return html.Div([
        html.Div([
            html.Img(src='assets/superform.png', className='company-logo'),
            html.H1("SuperVaults", className='brand-name'),
        ], className='brand-container'),
        
        html.Div([
            html.A("Documentation", href="https://docs.superform.xyz/supervaults/supervaults", className='nav-link'),
            html.A("Go To App →", href="https://www.superform.xyz/explore/", 
                  className='connect-wallet-btn'),
        ], className='nav-links'),
    ], className='header-banner')

def create_footer():
    return html.Footer([
        html.Div([
            html.P("﹩⒡"),
            html.Div([
                html.A("Twitter", href="https://x.com/superformxyz", className='footer-link'),
                html.A("Discord", href="https://discord.com/invite/superform", className='footer-link'),
                html.A("Privacy", href="https://help.superform.xyz/en/articles/8681749-privacy-policy", className='footer-link'),
                html.A("Terms", href="https://help.superform.xyz/en/articles/8693044-terms-of-service", className='footer-link')
            ], className='footer-links'),
        ], className='footer-content'),
    ], className='footer')

# -----------------------------------------------------------------------------
# UI Components - SuperVault Specific
# -----------------------------------------------------------------------------

def create_supervault_header(vault_info: dict) -> html.Div:
    """Creates a styled header for the supervault section"""
    try:
        chain_name = vault_info['chain']['name']
        chain_id = vault_info['chain']['id']
        chain_color = SuperformConfig(chain_id).chain_colors.get(chain_id, '#000000')
        vault_id = vault_info.get('id', '')
        
        return html.Div([
            html.Div([
                html.Img(src='assets/superform.png', className='supervault-logo'),
                html.Div([
                    html.H2(vault_info['friendly_name'], className='supervault-title'),
                    html.A(
                        "View on Superform →",
                        href=f"https://www.superform.xyz/vault/{vault_id}",
                        target="_blank",
                        className='vault-link'
                    )
                ], className='title-container'),
                html.Span(chain_name, className='chain-name')
            ], className='supervault-header-content')
        ], className='supervault-header', style={'borderColor': chain_color})
        
    except Exception as e:
        print(f"Error creating supervault header: {e}")
        return html.Div("Error loading supervault header", className='error-header')

def create_vault_tile(vault_info, allocation_percentage):
    """Creates a tile for each whitelisted vault"""
    protocol = vault_info.get('protocol', {})
    stats = vault_info.get('vault_statistics', {})
    
    is_inactive = allocation_percentage == 0
    tile_class = 'vault-tile inactive' if is_inactive else 'vault-tile'
    
    tile = html.Div([
        html.Div([
            html.Img(src=protocol.get('graphics', {}).get('icon', ''), 
                    className='protocol-icon'),
            html.Div([
                html.H4(vault_info['friendly_name']),
                html.P(f"{protocol.get('name', 'Unknown')} • {vault_info.get('yield_type', 'Unknown')}")
            ], className='vault-header-text')
        ], className='vault-header'),
        
        html.Div([
            html.Div([
                html.P("Allocation", className='metric-label'),
                html.H3(f"{allocation_percentage:.2f}%", className='metric-value'),
                html.P("APY (week)", className='metric-label'),
                html.H3(f"{stats.get('apy_week', 0):.2f}%", className='metric-value'),
            ], className='metrics-column'),
            
            html.Div([
                html.P("TVL", className='metric-label'),
                html.H3(f"${stats.get('tvl_now', 0):,.2f}", className='metric-value'),
                html.P("Price/Share", className='metric-label'),
                html.H3(f"${stats.get('pps_usd', 1):,.4f}", className='metric-value'),
            ], className='metrics-column'),
        ], className='metrics-grid'),
        
        html.Div([
            html.A("View on Superform →", 
                  href=f"https://www.superform.xyz/vault/{vault_info.get('id', '')}",
                  target="_blank",
                  className='vault-link'),
            html.A("View on Protocol Site →", 
                  href=vault_info.get('external_url', '#'),
                  target="_blank",
                  className='vault-link')
        ], className='vault-footer')
    ], className=tile_class)
    
    return tile

# -----------------------------------------------------------------------------
# Chart Components
# -----------------------------------------------------------------------------

def create_morpho_charts(morpho_data: dict) -> html.Div:
    """Creates pie chart and APY graph for Morpho markets"""
    allocations = morpho_data.get('state', {}).get('allocation', [])
    if not allocations:
        return None

    charts_div = []
    
    # Prepare data for pie chart
    markets_data = []
    for alloc in allocations:
        if not isinstance(alloc, dict):
            continue
            
        market = alloc.get('market', {})
        if not isinstance(market, dict):
            continue
            
        collateral = market.get('collateralAsset')
        if not isinstance(collateral, dict):
            continue
            
        supply_assets = float(alloc.get('supplyAssets', 0))
        lltv = float('0.' + market.get('lltv', '0')[:15]) * 100
        
        if supply_assets > 0:
            markets_data.append({
                'symbol': collateral.get('symbol', 'Unknown'),
                'supply': supply_assets,
                'lltv': lltv,
                'logo': collateral.get('logoURI', ''),
            })

    if markets_data:
        # Create the pie chart with responsive layout
        fig_pie = go.Figure(data=[go.Pie(
            labels=[m['symbol'] for m in markets_data],
            values=[m['supply'] for m in markets_data],
            hole=0.4,
            textinfo='percent',  # Only show percentage in the pie
            hovertemplate="<b>%{label}</b><br>" +
                         "Allocation: %{percent}<br>" +
                         "LLTV: %{customdata}%<extra></extra>",
            customdata=[f"{m['lltv']:.2f}" for m in markets_data],
        )])

        # Set initial layout
        fig_pie.update_layout(
            title={
                'text': "Collateral Asset Allocation",
                'y': 0.95,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': {
                    'size': 16,
                    'family': CHART_FONT_FAMILY,
                    'weight': 'bold'
                }
            },
            height=500,
            autosize=True,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5,
                font=dict(size=12, family=CHART_FONT_FAMILY),
                itemwidth=30,
                itemsizing='constant'
            ),
            margin=dict(t=50, b=50, l=20, r=20),
            font=dict(family=CHART_FONT_FAMILY)
        )

        # Get symbols with non-zero supply for APY graph
        active_symbols = {m['symbol'] for m in markets_data}

        # Prepare data for APY graph (only for active symbols)
        apy_data = []
        for alloc in allocations:
            if not isinstance(alloc, dict):
                continue
                
            market = alloc.get('market', {})
            if not isinstance(market, dict):
                continue
                
            collateral = market.get('collateralAsset')
            if not isinstance(collateral, dict):
                continue
                
            symbol = collateral.get('symbol', 'Unknown')
            if symbol not in active_symbols:
                continue
                
            state = market.get('state', {})
            if not isinstance(state, dict):
                continue
            
            supply_apy = float(state.get('supplyApy', 0)) * 100
            rewards = state.get('rewards', [])
            reward_apr = sum(float(reward.get('supplyApr', 0)) for reward in rewards) * 100
            total_apy = supply_apy + reward_apr
            
            apy_data.append({
                'symbol': symbol,
                'Total APY': total_apy,
                'Base APY': supply_apy,
                'Reward APR': reward_apr
            })

        if apy_data:
            # Sort apy_data by Total APY in descending order
            apy_data.sort(key=lambda x: x['Total APY'], reverse=True)
            
            # Update bar chart layout
            fig_apy = go.Figure()
            symbols = [d['symbol'] for d in apy_data]
            
            fig_apy.add_trace(go.Bar(
                name='Base APY',
                x=symbols,
                y=[d['Base APY'] for d in apy_data],
                marker_color='rgb(55, 83, 109)',
                width=0.6 
            ))
            
            fig_apy.add_trace(go.Bar(
                name='Reward APR',
                x=symbols,
                y=[d['Reward APR'] for d in apy_data],
                marker_color='rgb(26, 118, 255)',
                width=0.6 
            ))

            fig_apy.update_layout(
                title={
                    'text': 'APY Breakdown by Asset',
                    'y': 0.95,
                    'x': 0.5,
                    'xanchor': 'center',
                    'yanchor': 'top',
                    'font': {
                        'size': 16,
                        'family': CHART_FONT_FAMILY,
                        'weight': 'bold'
                    }
                },
                barmode='stack',
                yaxis=dict(
                    title='APY (%)',
                    zeroline=False,
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)',
                    tickformat='d',
                    tick0=5,
                    dtick=5,
                    ticktext=[str(i) for i in range(5, 201, 5)],  
                    tickvals=list(range(5, 201, 5)),  
                    range=[0, None],
                    tickfont=dict(family=CHART_FONT_FAMILY)
                ),
                margin=dict(t=80, b=50, l=20, r=20),
                height=400,
                autosize=True,
                legend=dict(
                    orientation="v", 
                    yanchor="top",
                    y=1,
                    xanchor="right",
                    x=1,            
                    font=dict(size=12, family=CHART_FONT_FAMILY),
                    bgcolor='rgba(255, 255, 255, 0.1)'
                ),
                bargap=0.15,
                bargroupgap=0.1,
                font=dict(family=CHART_FONT_FAMILY)
            )

            # Update hover template for both traces to show 2 decimal places
            fig_apy.update_traces(
                hovertemplate='%{y:.2f}%<extra></extra>'
            )

            # Return charts in a responsive layout
            return html.Div([
                html.Div([
                    dcc.Graph(
                        id='allocation-pie-chart',
                        figure=fig_pie,
                        config=COMMON_GRAPH_CONFIG,
                        responsive=True
                    ),
                ], className='chart-column'),
                html.Div([
                    dcc.Graph(
                        figure=fig_apy,
                        config=COMMON_GRAPH_CONFIG,
                        responsive=True
                    ),
                ], className='chart-column'),
            ], className='charts-container')

    return None

# -----------------------------------------------------------------------------
# Main Section Components
# -----------------------------------------------------------------------------

@retry_with_backoff()
def create_supervault_section(vault_data: dict) -> html.Div:
    """Creates a section for a supervault including its whitelisted vaults"""
    try:
        vault_info = vault_data['vault']
        chain_id = vault_info['chain']['id']
        vault_address = vault_info['contract_address']
        
        supervault = SuperVault(chain_id, vault_address)
        whitelisted_vaults = supervault.get_whitelisted_vaults()
        vault_allocations = supervault.get_supervault_data()
        
        # Create allocation mapping
        allocation_map = {}
        if len(vault_allocations) == 2:
            superform_ids, allocations = vault_allocations
            allocation_map = {str(id_): (alloc / 100) 
                            for id_, alloc in zip(superform_ids, allocations)}
        
        # Get data for each whitelisted vault
        superform_api = SuperformAPI()
        whitelisted_vault_data = []
        for superform_id in whitelisted_vaults:
            try:
                vault_data = superform_api.get_vault_data(superform_id)
                allocation = allocation_map.get(str(superform_id), 0)
                whitelisted_vault_data.append((vault_data, allocation))
            except Exception as e:
                print(f"Error fetching vault data for {superform_id}: {e}")
                continue
        
        # Sort by allocation
        whitelisted_vault_data.sort(key=lambda x: x[1], reverse=True)
        
        # Simplified Morpho detection
        morpho_charts = None
        morpho_vaults = [
            (vault_data, alloc) for vault_data, alloc in whitelisted_vault_data
            if (alloc > 0 and 
                vault_data.get('protocol', {}).get('name', '').lower() == 'morpho')
        ]
        
        if morpho_vaults:
            vault_data, _ = morpho_vaults[0]
            vault_address = vault_data.get('contract_address')
            if vault_address:
                morpho_data = Morpho().get_vault(vault_address)
                if morpho_data:
                    morpho_charts = create_morpho_charts(morpho_data)
        
        # Create the section with charts at the top
        section_children = [create_supervault_header(vault_info)]
        
        if morpho_charts:
            section_children.extend([
                html.Hr(),
                morpho_charts
            ])
        
        section_children.append(
            html.Div([
                create_vault_tile(vault_data, allocation)
                for vault_data, allocation in whitelisted_vault_data
            ], className='vault-grid')
        )
        
        return html.Div(section_children, className='supervault-section')
        
    except Exception as e:
        return html.Div(f"Error loading supervault section. Please try again later.", 
                       className='error-message')

# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------

# New function to load vaults directly
def load_vaults():
    try:
        logger.info("Loading vaults")
        supervaults = SuperformAPI().get_supervaults()
        
        if not supervaults:
            return html.Div("No vaults data available. Please try again later.", 
                          className='error-message')
        
        logger.info(f"Retrieved {len(supervaults)} supervaults")
        
        supervaults.sort(
            key=lambda x: float(x['vault']['vault_statistics'].get('tvl_now', 0)),
            reverse=True 
        )
        
        sections = []
        for vault_data in supervaults:
            try:
                section = create_supervault_section(vault_data)
                if section is not None:
                    sections.append(section)
            except Exception as e:
                logger.error(f"Error creating section for vault: {e}")
                continue
        
        if not sections:
            return html.Div("Error loading vaults. Please try again later.", 
                          className='error-message')
        
        logger.info(f"Successfully created {len(sections)} vault sections")
        return sections
        
    except Exception as e:
        logger.error(f"Error loading vaults: {e}")
        return html.Div("Error loading vaults. Please try again later.", 
                       className='error-message')

# -----------------------------------------------------------------------------
# App Initialization
# -----------------------------------------------------------------------------

app = Dash(
    __name__, 
    assets_folder='assets',
    title='SuperVaults', 
    update_title=None,
    suppress_callback_exceptions=True,
    meta_tags=[
        # Responsive viewport
        {
            'name': 'viewport',
            'content': 'width=device-width, initial-scale=1.0'
        },
        # General SEO
        {
            'name': 'description',
            'content': 'View more information on SuperVaults. Transparently earn more on your crypto.'
        },
        {
            'name': 'keywords',
            'content': 'Superform, SuperVaults, DeFi, yield farming, automated investing, crypto'
        },
    ]
)

app._favicon = 'superform.png'

def serve_layout():
    return html.Div([
        create_header(),
        html.Div(style={'height': '2rem'}),
        html.Div(id='loading-container', children=[
            dcc.Loading(
                id='loading',
                children=[html.Div(id='main-content')],
                type='circle',
                parent_className='loading-parent'
            ),
        ], className='main-content'),
        create_footer()
    ], className='app-container')

app.layout = serve_layout  

server = app.server

@app.callback(
    Output('main-content', 'children'),
    Input('loading', 'id')
)
def update_content(_):
    return load_vaults()

if __name__ == '__main__':
    app.run(debug=True)