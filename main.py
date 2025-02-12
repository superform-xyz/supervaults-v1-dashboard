import os
import json
from dash import Dash, html, dcc
import pandas as pd
from web3 import Web3
from functools import wraps
from libraries.superform import SuperVault, SuperformAPI, SuperformConfig
from libraries.morpho import Morpho
from libraries.euler import Euler
from dash.dependencies import Input, Output, State
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
    
    # Get shortened collateral addresses for labels
    collaterals = [f"{info['collateral'][:6]}...{info['collateral'][-4:]}" for info in vault_info]
    
    # Add traces for different LTV types
    fig_ltv.add_trace(go.Bar(
        name='Borrow LTV',
        x=collaterals,
        y=[info['borrowLTV'] for info in vault_info],
        marker_color='rgb(55, 83, 109)'
    ))
    
    fig_ltv.add_trace(go.Bar(
        name='Liquidation LTV',
        x=collaterals,
        y=[info['liquidationLTV'] for info in vault_info],
        marker_color='rgb(26, 118, 255)'
    ))
    
    fig_ltv.add_trace(go.Bar(
        name='Initial Liquidation LTV',
        x=collaterals,
        y=[info['initialLiquidationLTV'] for info in vault_info],
        marker_color='rgb(200, 83, 109)'
    ))
    
    fig_ltv.update_layout(
        title={
            'text': 'Collateral LTV Comparison',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        },
        barmode='group',
        yaxis_title='LTV %',
        xaxis_tickangle=45,  # Angle the address labels for better readability
        height=400,  # Increased height to accommodate angled labels
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
        charts = None
        active_vaults = [
            (vault_data, alloc) for vault_data, alloc in whitelisted_vault_data
            if alloc > 0
        ]
        
        for vault_data, _ in active_vaults:
            protocol_name = vault_data.get('protocol', {}).get('name', '').lower()
            vault_address = vault_data.get('contract_address')
            
            if protocol_name == 'morpho' and vault_address:
                morpho_data = Morpho().get_vault(vault_address)
                if morpho_data:
                    charts = create_morpho_charts(morpho_data)
                    break
            elif protocol_name == 'euler' and vault_address:
                chain_id = vault_data.get('chain', {}).get('id')
                if chain_id:
                    euler_data = Euler(chain_id).get_vault(vault_address)
                    if euler_data:
                        charts = create_euler_charts(euler_data)
                        break
        
        # Create the section with charts at the top
        section_children = [create_supervault_header(vault_info)]
        
        if charts:
            section_children.extend([
                html.Hr(),
                charts
            ])
        
        section_children.append(
            html.Div([
                create_vault_tile(vault_data, allocation)
                for vault_data, allocation in whitelisted_vault_data
            ], className='vault-grid')
        )
        
        total_time = time.time() - start_time
        print(f"Section complete: {total_time:.2f}s")
        return html.Div(section_children, className='supervault-section')
        
    except Exception:
        return html.Div("Error loading supervault section. Please try again later.", 
                       className='error-message')

# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------

def load_vaults():
    try:
        start_time = time.time()
        print("\n=== Performance Metrics ===")
        
        # Get supervaults
        api_start = time.time()
        supervaults = SuperformAPI().get_supervaults()
        print(f"API Init: {time.time() - api_start:.2f}s")
        
        if not supervaults:
            raise ValueError("No supervaults data received from API")
        
        time.sleep(0.5)
        
        # Initialize vault instances
        init_start = time.time()
        vault_instances = {}
        shared_api = SuperformAPI()
        
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
        
        def process_vault_data(vault_data, delay_start=0):
            try:
                process_start = time.time()
                if delay_start > 0:
                    time.sleep(delay_start)
                    
                vault_info = vault_data.get('vault')
                if not vault_info:
                    return None
                
                vault_address = vault_info['contract_address']
                supervault = vault_instances[vault_address]
                
                # Parallel fetch of whitelisted vaults and allocations
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    future_whitelisted = executor.submit(supervault.get_whitelisted_vaults)
                    future_allocations = executor.submit(supervault.get_supervault_data)
                    
                    whitelisted_vaults = future_whitelisted.result(timeout=10)
                    vault_allocations = future_allocations.result(timeout=10)
                
                if not whitelisted_vaults or not vault_allocations or len(vault_allocations) != 2:
                    return None
                
                superform_ids, allocations = vault_allocations
                allocation_map = {str(id_): (alloc / 100) 
                                for id_, alloc in zip(superform_ids, allocations)}
                
                # Fetch vault data in parallel batches
                whitelisted_vault_data = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [
                        executor.submit(
                            retry_with_backoff(retries=2, backoff_in_seconds=1)(
                                shared_api.get_vault_data
                            ),
                            superform_id
                        )
                        for superform_id in whitelisted_vaults
                    ]
                    
                    for future, superform_id in zip(futures, whitelisted_vaults):
                        try:
                            vault_data = future.result(timeout=10)
                            if vault_data:
                                allocation = allocation_map.get(str(superform_id), 0)
                                whitelisted_vault_data.append((vault_data, allocation))
                        except Exception as e:
                            print(f"Error fetching vault {superform_id}: {str(e)}")
                
                # Get protocol-specific data
                charts_data = None
                active_vaults = [(v, a) for v, a in whitelisted_vault_data if a > 0]
                
                for vault_data, _ in active_vaults:
                    protocol_name = vault_data.get('protocol', {}).get('name', '').lower()
                    vault_address = vault_data.get('contract_address')
                    
                    try:
                        if protocol_name == 'morpho' and vault_address:
                            morpho_data = Morpho().get_vault(vault_address)
                            if morpho_data:
                                charts_data = ('morpho', morpho_data)
                                break
                        elif protocol_name == 'euler' and vault_address:
                            chain_id = vault_data.get('chain', {}).get('id')
                            if chain_id:
                                euler_data = Euler(chain_id).get_vault(vault_address)
                                if euler_data:
                                    charts_data = ('euler', euler_data)
                                    break
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"Error fetching protocol data for {protocol_name}: {str(e)}")
                        continue
                
                # Before creating UI, verify we have all needed data
                if not whitelisted_vault_data:
                    print("No whitelisted vault data available")
                    return None
                
                print(f"Vault Processing: {time.time() - process_start:.2f}s")
                return create_supervault_section_ui(vault_info, whitelisted_vault_data, charts_data)
                
            except Exception as e:
                print(f"Error: {str(e)}")
                return None
        
        # Process vaults
        processing_start = time.time()
        sections = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_vault = {
                executor.submit(
                    process_vault_data, 
                    vault_data,
                    delay_start=i * 1.0
                ): i
                for i, vault_data in enumerate(supervaults[:15])
                if vault_data['vault']['contract_address'] in vault_instances
            }
            
            for future in concurrent.futures.as_completed(future_to_vault):
                i = future_to_vault[future]
                try:
                    section = future.result(timeout=60)
                    if section is not None:
                        sections[i] = section
                except Exception as e:
                    print(f"Failed vault {i}: {str(e)}")
        
        print(f"Initial Processing: {time.time() - processing_start:.2f}s")
        
        # Retry failed sections if any
        retry_start = time.time()
        failed_indices = [
            i for i, vault_data in enumerate(supervaults[:15])
            if i not in sections and vault_data['vault']['contract_address'] in vault_instances
        ]
        
        if failed_indices:
            print(f"\n=== Retrying {len(failed_indices)} Vaults ===")
            for retry_attempt in range(2):
                if not failed_indices:
                    break
                
                still_failed = []
                for i in failed_indices:
                    try:
                        section = process_vault_data(supervaults[i])
                        if section is not None:
                            sections[i] = section
                        else:
                            still_failed.append(i)
                        time.sleep(0.5)
                    except Exception as e:
                        still_failed.append(i)
                
                failed_indices = still_failed
            
            print(f"Retry Processing: {time.time() - retry_start:.2f}s")
        
        print(f"Total Time: {time.time() - start_time:.2f}s\n")
        
        sorted_sections = [section for i, section in sorted(sections.items())]
        return sorted_sections if sorted_sections else html.Div("No vaults available", className='error-message')
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return html.Div("Error loading vaults", className='error-message')

def create_supervault_section_ui(vault_info: dict, whitelisted_vault_data: list, charts_data: tuple) -> html.Div:
    """Creates the UI components for a supervault section"""
    try:
        # Verify vault_info has required fields
        if not vault_info.get('friendly_name'):
            return None
            
        # Sort by allocation
        whitelisted_vault_data.sort(key=lambda x: x[1], reverse=True)
        
        # Create charts if we have protocol data
        charts = None
        if charts_data:
            protocol_type, protocol_data = charts_data
            if protocol_type == 'morpho':
                charts = create_morpho_charts(protocol_data)
            elif protocol_type == 'euler':
                charts = create_euler_charts(protocol_data)
        
        # Create the section with charts at the top
        try:
            section_children = [create_supervault_header(vault_info)]
        except Exception as e:
            print(f"Error creating header: {str(e)}")
            return None
        
        if charts:
            section_children.extend([
                html.Hr(),
                charts
            ])
        
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
        create_header(),
        html.Div(style={'height': '2rem'}),
        html.Div(id='loading-container', children=[
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