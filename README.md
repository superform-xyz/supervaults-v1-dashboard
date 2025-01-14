# SuperVaults Dashboard

A real-time dashboard built with Dash/Plotly to visualize and monitor SuperVaults performance and allocations.

## Overview

This dashboard provides a comprehensive view of SuperVaults, displaying:
- Current allocations across whitelisted vaults
- Performance metrics (APY, TVL)
- Detailed lending market analytics including:
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

- **Interactive Charts**: 
  - Pie charts showing asset allocations
  - Stacked bar charts for APY breakdown
- **Vault Details**:
  - Protocol information
  - Current allocations
  - Performance metrics
  - Direct links to Superform and protocol sites
- **Responsive Design**: Optimized for both desktop and mobile viewing