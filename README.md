# SuperVaults Dashboard

A real-time dashboard built with Dash/Plotly to visualize and monitor SuperVaults performance and allocations.

## Overview

This dashboard provides a comprehensive view of SuperVaults, displaying:
- Current allocations across whitelisted vaults
- Performance metrics (APY, TVL)
- Detailed Morpho market analytics including:
  - Collateral asset allocation visualization
  - APY breakdown by asset (Base APY + Reward APR)

## Setup

1. Create a `.env.local` file with the following variables:
    - `SUPERFORM_API_KEY`: Your Superform API key
2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3. Run the dashboard:
    ```bash
    python main.py
    ```

## Features

- **Real-time Data**: Updates every 5 minutes
- **Interactive Charts**: 
  - Pie charts showing asset allocations
  - Stacked bar charts for APY breakdown
- **Vault Details**:
  - Protocol information
  - Current allocations
  - Performance metrics
  - Direct links to Superform and protocol sites
- **Responsive Design**: Optimized for both desktop and mobile viewing

## Technical Stack

- **Frontend**: Dash/Plotly
- **Data Sources**:
  - Superform API
  - Morpho GraphQL API
  - Web3 integration for on-chain data
- **Key Libraries**:
  - `dash`: Web application framework
  - `plotly`: Data visualization
  - `web3`: Blockchain interaction
  - `pandas`: Data manipulation
  - `gql`: GraphQL client

## Architecture

- **Caching**: Implements LRU cache with 5-minute timeout
- **Error Handling**: Retry mechanism with exponential backoff
- **Logging**: Configured for both console and file output
- **Modular Design**: Separated into utility, UI, and chart components