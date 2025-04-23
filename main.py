import os
import json
from dash import Dash, html, dcc
import pandas as pd
from dash.dependencies import Input, Output, State
from web3 import Web3
from functools import wraps
from libraries.superform import SuperVault, SuperformAPI, SuperformConfig
from libraries.morpho import Morpho
from libraries.euler import Euler
from typing import List, Dict, Any
import plotly.graph_objects as go
import plotly.express as px
import concurrent.futures
import random
import sys
import time 
import traceback

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

def retry_with_backoff(retries=3, backoff_in_seconds=1, timeout=30):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            start_time = time.time()
            while True:
                try:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Operation timed out after {timeout}s")
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        print(f"Failed after {retries} attempts: {str(e)}")
                        raise
                    wait = (backoff_in_seconds * 2 ** x + 
                           random.uniform(0, 1))
                    print(f"Attempt {x + 1} failed with error: {str(e)}, retrying in {wait:.2f}s")
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
            html.A([
                html.Img(src='assets/superform.png', className='company-logo'),
                html.H1("SuperVaults", className='brand-name'),
            ], href="/", className='brand-link'),
        ], className='brand-container'),
        
        html.Div([
            html.A("Integrations", href="/integrations", className='nav-link'),
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
        return html.Div("Error loading supervault header", className='error-header')

def create_vault_tile(vault_data, allocation_percentage):
    """Creates a tile for each whitelisted vault"""
    try:
        protocol = vault_data.get('protocol', {})
        stats = vault_data.get('vault_statistics', {})
        
        # Verify required fields
        if not vault_data.get('friendly_name'):
            return None
            
        is_inactive = allocation_percentage == 0
        tile_class = 'vault-tile inactive' if is_inactive else 'vault-tile'
        
        tile = html.Div([
            html.Div([
                html.Img(src=protocol.get('graphics', {}).get('icon', ''), 
                        className='protocol-icon'),
                html.Div([
                    html.H4(vault_data['friendly_name']),
                    html.P(f"{protocol.get('name', 'Unknown')} • {vault_data.get('yield_type', 'Unknown')}")
                ], className='vault-header-text')
            ], className='vault-header'),
            
            html.Div([
                html.Div([
                    html.P("Allocation", className='metric-label'),
                    html.H3(f"{allocation_percentage:.2f}%", className='metric-value')
                ], className='metrics-column'),
                
                html.Div([
                    html.P("TVL", className='metric-label'),
                    html.H3(f"${stats.get('tvl_now', 0):,.2f}", className='metric-value')
                ], className='metrics-column'),
            ], className='metrics-grid'),
            
            html.Div([
                html.A("View on Superform →", 
                      href=f"https://www.superform.xyz/vault/{vault_data.get('id', '')}",
                      target="_blank",
                      className='vault-link'),
                html.A("View on Protocol Site →", 
                      href=vault_data.get('external_url', '#'),
                      target="_blank",
                      className='vault-link')
            ], className='vault-footer')
        ], className=tile_class)
        
        return tile
        
    except Exception as e:
        print(f"Error creating tile: {str(e)}")
        return None

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
                'text': "Morpho Collateral Asset Allocation",
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
            height=400,
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
            paper_bgcolor='white',
            plot_bgcolor='white',
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
                    'text': 'Morpho APY Breakdown by Asset',
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
                margin=dict(t=50, b=50, l=50, r=20),
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
                paper_bgcolor='white',
                plot_bgcolor='white',
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

def create_euler_charts(vault_info: List[Dict[str, Any]]) -> html.Div:
    """Creates charts for Euler vault LTV data"""
    if not vault_info:
        return None

    # Create LTV comparison chart
    fig_ltv = go.Figure()
    
    # Get collateral names for labels
    collateral_names = [info['collateralName'] for info in vault_info]
    
    # Add traces for different LTV types
    fig_ltv.add_trace(go.Bar(
        name='Borrow LTV',
        x=collateral_names,
        y=[info['borrowLTV'] for info in vault_info],
        marker_color='rgb(55, 83, 109)'
    ))
    
    fig_ltv.add_trace(go.Bar(
        name='Liquidation LTV',
        x=collateral_names,
        y=[info['liquidationLTV'] for info in vault_info],
        marker_color='rgb(26, 118, 255)'
    ))
    
    fig_ltv.update_layout(
        title={
            'text': 'Euler Collateral Assets',
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
        barmode='group',
        yaxis=dict(
            title='LTV %',
            zeroline=False,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            tickfont=dict(family=CHART_FONT_FAMILY)
        ),
        xaxis=dict(
            tickangle=45,
            tickfont=dict(family=CHART_FONT_FAMILY)
        ),
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
        margin=dict(t=50, b=100, l=50, r=20),
        paper_bgcolor='white',
        plot_bgcolor='white',
        font=dict(family=CHART_FONT_FAMILY)
    )

    return html.Div([
        html.Div([
            dcc.Graph(
                figure=fig_ltv,
                config=COMMON_GRAPH_CONFIG,
                responsive=True
            ),
        ], className='chart-column'),
    ], className='charts-container')

# -----------------------------------------------------------------------------
# Page Components
# -----------------------------------------------------------------------------

def create_integrations_page():
    """Creates the integrations page content with three main sections for earning CRED"""
    return html.Div([
        html.H2("Earn more with Superform Exploration", className="page-title"),
        html.P("Discover the best ways to earn CRED.", className="page-description"),
        
        # Pendle and Spectra logos
        html.Div([
            html.Img(src="assets/pendle.png", className="partner-logo"),
            html.Img(src="assets/spectra.png", className="partner-logo"),
            html.Img(src="assets/term.png", className="partner-logo"),
            html.Img(src="assets/napier.svg", className="partner-logo"),
            html.Img(src="assets/royco.svg", className="partner-logo"),
            html.Img(src="assets/piggy.png", className="partner-logo"),
        ], className="partner-logos-container"),
        
        html.H3("SuperVaults", className="section-title"),
        
        # SuperUSDC on Ethereum Section
        html.Div([
            html.H4("SuperUSDC on Ethereum", className="integration-subsection-title"),
            
            html.Div([
                # Card 1: Deposit into SuperUSDC
                html.Div([
                    html.H5("Deposit into SuperUSDC on Superform", className="card-title"),
                    html.P([
                        html.Strong("20x CRED"), 
                        " + up to ", 
                        html.Strong("10x CRED TVL Boost"), 
                        " & ", 
                        html.Strong("5x CRED Loyalty Boost")
                    ], className="card-description"),
                    html.A("SuperUSDC Vault", href="https://www.superform.xyz/vault/vL7k-5ZgYCoFgi6kz2jIJ/", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 2: Provide SuperUSDC Liquidity on Pendle
                html.Div([
                    html.H5("Provide SuperUSDC Liquidity on Pendle", className="card-title"),
                    html.P([
                        html.Strong("50x CRED"), 
                        " + Pool APY"
                    ], className="card-description"),
                    html.P("Expiry: April 17th", className="expiry-text"),
                    html.A("Pendle Liquidity", href="https://app.pendle.finance/trade/pools/0x1bd1ae9d7a377e63cd0c584a2c42b8c614937e81/zap/in?chain=ethereum", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 3: Hold SuperUSDC Pendle YT
                html.Div([
                    html.H5("Hold SuperUSDC Pendle YT", className="card-title"),
                    html.P([
                        html.Strong("50x CRED")
                    ], className="card-description"),
                    html.P("Expiry: April 17th", className="expiry-text"),
                    html.A("Pendle YT", href="https://app.pendle.finance/trade/markets/0x1bd1ae9d7a377e63cd0c584a2c42b8c614937e81/swap?view=yt&chain=ethereum", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 4: Provide SuperUSDC Liquidity on Spectra
                html.Div([
                    html.H5("Provide SuperUSDC Liquidity on Spectra", className="card-title"),
                    html.P([
                        html.Strong("50x CRED"), 
                        " + Pool APY"
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Spectra Liquidity", href="https://app.spectra.finance/pools/eth:0xd7e163a91d11cfa2b4059f1626ccd6e33b143cbc", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 5: Hold SuperUSDC YT on Spectra
                html.Div([
                    html.H5("Hold SuperUSDC YT on Spectra", className="card-title"),
                    html.P([
                        html.Strong("50x CRED")
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Spectra YT", href="https://app.spectra.finance/trade-yield/eth:0xd7e163a91d11cfa2b4059f1626ccd6e33b143cbc", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 6: Participate in Term Auction for PT-ysUSDC
                html.Div([
                    html.H5("Participate in Term Auction for PT-ysUSDC", className="card-title"),
                    html.P([
                        html.Strong("30x CRED"), 
                        " + Term APY"
                    ], className="card-description"),
                    html.A("Term Auction", href="https://app.term.finance/auctions/0xb3728e7e1190f8673a72ec53a30fbb21448047d2/1", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 7: Lock SuperUSDC on Royco
                html.Div([
                    html.H5("Lock SuperUSDC on Royco for 3 months (Closed)", className="card-title"),
                    html.P([
                        html.Strong("30x CRED")
                    ], className="card-description"),
                    html.P("End Date: April 20th", className="expiry-text"),
                    html.A("Royco Lock", href="https://app.royco.org/market/1/0/0xf98c40038e95042341a5e0f0d9fa4cc7a32a839f8645ebb91dd770f8578e2280", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 8: Provide SuperUSDC Liquidity on Napier
                html.Div([
                    html.H5("Provide SuperUSDC Liquidity on Napier", className="card-title"),
                    html.P([
                        html.Strong("50x CRED"), 
                        " + Pool APY"
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Napier Liquidity", href="https://app.napier.finance/user/trade/1/0xddfb1bcfe41d8bd90fa57ee2cfc8ec7c94981ced/pt", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 9: Hold SuperUSDC Napier YT
                html.Div([
                    html.H5("Hold SuperUSDC Napier YT", className="card-title"),
                    html.P([
                        html.Strong("50x CRED")
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Napier YT", href="https://app.napier.finance/user/trade/1/0xddfb1bcfe41d8bd90fa57ee2cfc8ec7c94981ced/yt", target="_blank", className="card-link")
                ], className="integration-card"),
            ], className="integration-cards-grid"),
        ], className="integration-section"),
        
        # SuperUSDC on Base Section
        html.Div([
            html.H4("SuperUSDC on Base", className="integration-subsection-title"),
            
            html.Div([
                # Card 1: Deposit into SuperUSDC on Base
                html.Div([
                    html.H5("Deposit into SuperUSDC on Superform", className="card-title"),
                    html.P([
                        html.Strong("20x CRED"), 
                        " + up to ", 
                        html.Strong("10x CRED TVL Boost"), 
                        " & ", 
                        html.Strong("5x CRED Loyalty Boost")
                    ], className="card-description"),
                    html.A("SuperUSDC Vault", href="https://www.superform.xyz/vault/zLVQbgScIbXJuSz-NNsK-/", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 2: Lock SuperUSDC on Royco
                html.Div([
                    html.H5("Lock SuperUSDC on Royco for 10 weeks", className="card-title"),
                    html.P([
                        html.Strong("30x CRED")
                    ], className="card-description"),
                    html.P("End Date: April 20th", className="expiry-text"),
                    html.A("Royco Lock", href="https://app.royco.org/market/8453/0/0x18493e771a4fd1cc17f01ec9f12cc3058bd4e30fda4affdd3e2c11ec6a557c8c", target="_blank", className="card-link")
                ], className="integration-card"),
            ], className="integration-cards-grid"),
        ], className="integration-section"),
        
        # SuperETH on Ethereum Section
        html.Div([
            html.H4("SuperETH on Ethereum", className="integration-subsection-title"),
            
            html.Div([
                # Card 1: Deposit into SuperETH
                html.Div([
                    html.H5("Deposit into SuperETH on Superform", className="card-title"),
                    html.P([
                        html.Strong("20x CRED"), 
                        " + up to ", 
                        html.Strong("10x CRED TVL Boost"), 
                        " & ", 
                        html.Strong("5x CRED Loyalty Boost")
                    ], className="card-description"),
                    html.A("SuperETH Vault", href="https://www.superform.xyz/vault/8x0dWMdugEMCvyTC1mfdx/", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 2: Provide SuperETH Liquidity on Spectra
                html.Div([
                    html.H5("Provide SuperETH Liquidity on Spectra", className="card-title"),
                    html.P([
                        html.Strong("50x CRED"), 
                        " + Pool APY"
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Spectra Liquidity", href="https://app.spectra.finance/pools/eth:0x1825b0ffb79093be293b9899f33ae7f665d872ce", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 3: Hold SuperETH YT on Spectra
                html.Div([
                    html.H5("Hold SuperETH YT on Spectra", className="card-title"),
                    html.P([
                        html.Strong("50x CRED")
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Spectra YT", href="https://app.spectra.finance/trade-yield/eth:0x1825b0ffb79093be293b9899f33ae7f665d872ce", target="_blank", className="card-link")
                ], className="integration-card"),
            ], className="integration-cards-grid"),
        ], className="integration-section"),
        
        html.Hr(className="section-divider"),
        
        # PIGGY Section
        html.Div([
            html.H4("$PIGGY", className="integration-subsection-title"),
            
            html.Div([
                # Card 1: Deposit PIGGY into Animal Farm
                html.Div([
                    html.H5("Deposit $PIGGY into Animal Farm on Superform", className="card-title"),
                    html.P([
                        html.Strong("10x CRED"), 
                        " + up to ", 
                        html.Strong("10x CRED TVL Boost"), 
                        " & ", 
                        html.Strong("5x CRED Loyalty Boost")
                    ], className="card-description"),
                    html.A("Animal Farm", href="https://www.superform.xyz/vault/jwkQfbPyh33AYFE3iF5II/", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 2: Deposit PIGGY + ETH to Slop Bucket
                html.Div([
                    html.H5("Deposit $PIGGY + $ETH to Slop Bucket", className="card-title"),
                    html.P([
                        html.Strong("15x CRED"), 
                        " + Pool APY"
                    ], className="card-description"),
                    html.A("Slop Bucket", href="https://www.superform.xyz/piggy/", target="_blank", className="card-link")
                ], className="integration-card"),
                
                # Card 3: Lock PIGGY on Royco
                html.Div([
                    html.H5("Lock $PIGGY on Royco for 10 weeks (Closed)", className="card-title"),
                    html.P([
                        html.Strong("15x CRED"), 
                        html.I(" (at $3M MC)")
                    ], className="card-description"),
                    html.P("Expiry: April 20th", className="expiry-text"),
                    html.A("Royco Lock", href="https://app.royco.org/market/8453/0/0x1b467d65fde4ec8988e8df1706d0f9e028db8d41e14d10fbbd7b194e5744ac59", target="_blank", className="card-link")
                ], className="integration-card"),
            ], className="integration-cards-grid"),
        ], className="integration-section piggy-section"),
        
        # Simple track your CRED link with note
        html.Div([
            html.P(
                [
                    html.Strong("Note:"), 
                    " CRED earned from Pendle, Spectra, Term, Royco, and Napier does not stack with TVL or loyalty boosts and will be awarded at the end of the season."
                ], 
                className="note-text"
            )
        ], className="cred-track-section"),
        
    ], className="integrations-container")

# -----------------------------------------------------------------------------
# Main Section Components
# -----------------------------------------------------------------------------

@retry_with_backoff()
def create_supervault_section(vault_data: dict) -> html.Div:
    """Creates a section for a supervault including its whitelisted vaults"""
    start_time = time.time()
    try:
        vault_info = vault_data['vault']
        chain_id = vault_info['chain']['id']
        vault_address = vault_info['contract_address']
        
        print(f"\nProcessing vault {vault_address} on chain {chain_id}")
        
        sv_start = time.time()
        supervault = SuperVault(chain_id, vault_address)
        try:
            whitelisted_vaults = supervault.get_whitelisted_vaults()
            if not whitelisted_vaults:
                print(f"No whitelisted vaults found for {vault_address}")
                return None
        except Exception as e:
            print(f"Error getting whitelisted vaults: {str(e)}")
            return None
            
        try:
            vault_allocations = supervault.get_supervault_data()
            if not vault_allocations or len(vault_allocations) != 2:
                print(f"Invalid vault allocations for {vault_address}: {vault_allocations}")
                return None
        except Exception as e:
            print(f"Error getting vault allocations: {str(e)}")
            return None
            
        sv_time = time.time() - sv_start
        print(f"SuperVault operations: {sv_time:.2f}s")
        
        # Create allocation mapping
        superform_ids, allocations = vault_allocations
        allocation_map = {str(id_): (alloc / 100) 
                        for id_, alloc in zip(superform_ids, allocations)}
        
        api_start = time.time()
        superform_api = SuperformAPI()
        
        # Parallelize vault data fetching with balanced settings
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            batch_size = 2  # Slightly reduced batch size
            whitelisted_vault_data = []
            
            for i in range(0, len(whitelisted_vaults), batch_size):
                batch = whitelisted_vaults[i:i+batch_size]
                futures = []
                
                for superform_id in batch:
                    future = executor.submit(
                        retry_with_backoff(retries=2, backoff_in_seconds=1)(
                            superform_api.get_vault_data
                        ), 
                        superform_id
                    )
                    futures.append((future, superform_id))
                
                for future, superform_id in futures:
                    try:
                        vault_data = future.result(timeout=10)  # Add timeout
                        if vault_data:
                            allocation = allocation_map.get(str(superform_id), 0)
                            whitelisted_vault_data.append((vault_data, allocation))
                        else:
                            print(f"No data returned for vault {superform_id}")
                    except concurrent.futures.TimeoutError:
                        print(f"Timeout fetching vault {superform_id}")
                    except Exception as e:
                        print(f"Error fetching vault {superform_id}: {str(e)}")
                
                time.sleep(0.2)  # Slight increase in delay
        
        if not whitelisted_vault_data:
            print(f"No valid vault data collected for {vault_address}")
            return None
            
        # Sort by allocation
        whitelisted_vault_data.sort(key=lambda x: x[1], reverse=True)
        
        # Detect and create charts for protocols
        charts_data = []
        active_vaults = [
            (vault_data, alloc) for vault_data, alloc in whitelisted_vault_data
            if alloc > 0
        ]
        
        # Track which protocols we've processed to avoid duplicates
        processed_protocols = set()
        
        print(f"\nChecking protocols for vault {vault_address}:")
        for vault_data, allocation in active_vaults:
            protocol_name = vault_data.get('protocol', {}).get('name', '').lower()
            vault_address = vault_data.get('contract_address')
            
            print(f"Found protocol: {protocol_name} with allocation {allocation}%")
            
            # Skip if we've already processed this protocol
            if protocol_name in processed_protocols:
                print(f"Skipping {protocol_name} - already processed")
                continue
                
            try:
                if protocol_name == 'morpho' and vault_address:
                    print(f"Processing Morpho vault: {vault_address}")
                    morpho_data = Morpho().get_vault(vault_address)
                    if morpho_data:
                        morpho_charts = create_morpho_charts(morpho_data)
                        if morpho_charts:
                            charts_data.append(('morpho', morpho_charts))
                            processed_protocols.add('morpho')
                            print("Successfully added Morpho charts")
                elif protocol_name == 'euler' and vault_address:
                    print(f"Processing Euler vault: {vault_address}")
                    chain_id = vault_data.get('chain', {}).get('id')
                    if chain_id:
                        euler_data = Euler(chain_id).get_vault_ltv(vault_address)
                        if euler_data:
                            euler_charts = create_euler_charts(euler_data)
                            if euler_charts:
                                charts_data.append(('euler', euler_charts))
                                processed_protocols.add('euler')
                                print("Successfully added Euler charts")
            except Exception as e:
                print(f"Error processing {protocol_name} vault {vault_address}: {str(e)}")
                continue
        
        # Create the section with charts at the top
        section_children = [create_supervault_header(vault_info)]
        
        if charts_data:
            section_children.append(html.Hr())
            for protocol_type, chart in charts_data:
                section_children.append(chart)
        
        section_children.append(
            html.Div([
                create_vault_tile(vault_data, allocation)
                for vault_data, allocation in whitelisted_vault_data
            ], className='vault-grid')
        )
        
        total_time = time.time() - start_time
        print(f"Section complete: {total_time:.2f}s")
        return html.Div(section_children, className='supervault-section')
        
    except Exception as e:
        print(f"Error loading supervault section: {str(e)}")
        return html.Div("Error loading supervault section. Please try again later.", 
                       className='error-message')

# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------

def process_vault_data(vault_data, all_vaults_data, vault_instances):
    """Process a single vault's data without concurrency since we're just doing memory lookups"""
    try:
        process_metrics = {}
        process_start = time.time()

        vault_info = vault_data.get('vault')
        if not vault_info:
            return None
        
        vault_address = vault_info['contract_address']
        supervault = vault_instances[vault_address]
        
        # Time blockchain calls
        blockchain_start = time.time()
        whitelisted_vaults = supervault.get_whitelisted_vaults()
        vault_allocations = supervault.get_supervault_data()
        process_metrics['blockchain_calls'] = time.time() - blockchain_start
        
        if not whitelisted_vaults or not vault_allocations or len(vault_allocations) != 2:
            return None
        
        # Time data processing
        processing_start = time.time()
        superform_ids, allocations = vault_allocations
        allocation_map = {str(id_): (alloc / 100) 
                        for id_, alloc in zip(superform_ids, allocations)}
        
        # Simple memory lookup for each vault
        whitelisted_vault_data = []
        for superform_id in whitelisted_vaults:
            vault = next(
                (v for v in all_vaults_data if str(v.get('superform_id')) == str(superform_id)), 
                None
            )
            if vault:
                allocation = allocation_map.get(str(superform_id), 0)
                whitelisted_vault_data.append((vault, allocation))
            else:
                print(f"Vault {superform_id} not found in pre-fetched data")
        process_metrics['data_processing'] = time.time() - processing_start

        # Time protocol-specific API calls
        protocol_start = time.time()
        charts_data = []
        active_vaults = [(v, a) for v, a in whitelisted_vault_data if a > 0]
        
        # Track which protocols we've processed to avoid duplicates
        processed_protocols = set()
        
        for vault_data, _ in active_vaults:
            protocol_name = vault_data.get('protocol', {}).get('name', '').lower()
            vault_address = vault_data.get('contract_address')
            
            # Skip if we've already processed this protocol
            if protocol_name in processed_protocols:
                continue
                
            try:
                if protocol_name == 'morpho' and vault_address:
                    morpho_data = Morpho().get_vault(vault_address)
                    if morpho_data:
                        morpho_charts = create_morpho_charts(morpho_data)
                        if morpho_charts:
                            charts_data.append(('morpho', morpho_charts))
                            processed_protocols.add('morpho')
                elif protocol_name == 'euler' and vault_address:
                    chain_id = vault_data.get('chain', {}).get('id')
                    if chain_id:
                        euler_data = Euler(chain_id).get_vault_ltv(vault_address)
                        if euler_data:
                            euler_charts = create_euler_charts(euler_data)
                            if euler_charts:
                                charts_data.append(('euler', euler_charts))
                                processed_protocols.add('euler')
            except Exception as e:
                print(f"Error fetching protocol data for {protocol_name}: {str(e)}")
                continue
                
        process_metrics['protocol_calls'] = time.time() - protocol_start
        
        if not whitelisted_vault_data:
            print("No whitelisted vault data available")
            return None

        # Time UI creation
        ui_start = time.time()
        section = create_supervault_section_ui(vault_info, whitelisted_vault_data, charts_data)
        process_metrics['ui_creation'] = time.time() - ui_start
        
        process_metrics['total'] = time.time() - process_start
        print(f"\nVault {vault_address} processing times:")
        print(f"  Blockchain calls: {process_metrics['blockchain_calls']:.2f}s")
        print(f"  Data processing: {process_metrics['data_processing']:.2f}s")
        print(f"  Protocol calls: {process_metrics['protocol_calls']:.2f}s")
        print(f"  UI creation: {process_metrics['ui_creation']:.2f}s")
        print(f"  Total: {process_metrics['total']:.2f}s")
        
        return section
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def load_vaults():
    try:
        start_time = time.time()
        print("\n=== Performance Metrics ===")
        
        # Get supervaults and all vaults data at the start
        api_start = time.time()
        shared_api = SuperformAPI()
        
        # Fetch both supervaults and all vaults data in parallel (using 2 of 4 available threads)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_supervaults = executor.submit(shared_api.get_supervaults)
            future_all_vaults = executor.submit(shared_api.get_vaults)
            
            supervaults = future_supervaults.result()
            all_vaults_data = future_all_vaults.result()
        
        if not supervaults or not all_vaults_data:
            raise ValueError("Failed to fetch required data from API")
            
        supervaults.sort(key=lambda x: 0 if x['vault']['chain']['id'] == 1 else 1)
        print(f"API Init: {time.time() - api_start:.2f}s")
        
        # Initialize vault instances
        init_start = time.time()
        vault_instances = {}
        for vault_data in supervaults[:15]:
            try:
                vault_info = vault_data['vault']
                vault_instances[vault_info['contract_address']] = SuperVault(
                    vault_info['chain']['id'], 
                    vault_info['contract_address']
                )
            except Exception:
                continue
        
        print(f"Vault Init: {time.time() - init_start:.2f}s")
        
        if not vault_instances:
            raise ValueError("No vault instances could be initialized")
        
        # Process vaults in parallel (using all 4 available threads)
        processing_start = time.time()
        sections = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_vault = {
                executor.submit(
                    process_vault_data, 
                    vault_data,
                    all_vaults_data,
                    vault_instances
                ): i
                for i, vault_data in enumerate(supervaults[:15])
                if vault_data['vault']['contract_address'] in vault_instances
            }
            
            for future in concurrent.futures.as_completed(future_to_vault):
                i = future_to_vault[future]
                try:
                    section = future.result()
                    if section is not None:
                        sections[i] = section
                except Exception as e:
                    print(f"Failed vault {i}: {str(e)}")
        
        print(f"Processing: {time.time() - processing_start:.2f}s")
        print(f"Total Time: {time.time() - start_time:.2f}s\n")
        
        sorted_sections = [section for i, section in sorted(sections.items())]
        return sorted_sections if sorted_sections else html.Div("No vaults available", className='error-message')
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return html.Div("Error loading vaults", className='error-message')

def create_supervault_section_ui(vault_info: dict, whitelisted_vault_data: list, charts_data: list) -> html.Div:
    """Creates the UI components for a supervault section"""
    try:
        # Verify vault_info has required fields
        if not vault_info.get('friendly_name'):
            return None
            
        # Sort by allocation
        whitelisted_vault_data.sort(key=lambda x: x[1], reverse=True)
        
        # Create the section with charts at the top
        try:
            section_children = [create_supervault_header(vault_info)]
        except Exception as e:
            print(f"Error creating header: {str(e)}")
            return None
        
        # Add charts if we have them
        if charts_data:
            section_children.append(html.Hr())
            for protocol_type, chart in charts_data:
                section_children.append(chart)
        
        try:
            # Create tiles with error handling
            vault_tiles = []
            for vault_data, allocation in whitelisted_vault_data:
                tile = create_vault_tile(vault_data, allocation)
                if tile is not None:
                    vault_tiles.append(tile)
                    
            if not vault_tiles:
                return None
                
            vault_grid = html.Div(vault_tiles, className='vault-grid')
            section_children.append(vault_grid)
            
        except Exception as e:
            print(f"Error creating vault tiles: {str(e)}")
            return None
        
        return html.Div(section_children, className='supervault-section')
        
    except Exception as e:
        print(f"Error creating UI: {str(e)}")
        return None

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
        dcc.Location(id='url', refresh=False),
        create_header(),
        html.Div(style={'height': '2rem'}),
        html.Div(id='page-content'),
        create_footer()
    ], className='app-container')

app.layout = serve_layout  

server = app.server

@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname')
)
def display_page(pathname):
    if pathname == '/integrations':
        return create_integrations_page()
    else:
        # Main page content
        return html.Div(id='loading-wrapper', children=[
            dcc.Loading(
                id='loading',
                children=[html.Div(id='main-content')],
                type='circle',
            ),
            html.Div(
                "Pulling live data...", 
                id='loading-text',
                className='loading-text'
            )
        ], className='main-content')

@app.callback(
    Output('main-content', 'children'),
    Input('loading', 'id')
)
def update_content(_):
    return load_vaults()

@app.callback(
    Output('loading-text', 'style'),
    Input('main-content', 'children')
)
def hide_loading_text(content):
    if content is not None:
        return {'display': 'none'}
    return {'display': 'block'}

if __name__ == '__main__':
    app.run(debug=True)