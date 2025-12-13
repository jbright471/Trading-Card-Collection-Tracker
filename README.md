# Multi-Game Card Tracker

A powerful Python script to track the value of your **Magic: The Gathering** and **Yu-Gi-Oh!** collections.

## Features

*   **Two Games, One Tracker**: Combines MTG and YGO into one report.
*   **📈 Price History**: Tracks your total collection value over time and generates a line graph.
*   **🔼 Price Current Trends**: Shows ▲/▼ arrows to indicate if an individual card's price has changed since the last run.
*   **🖼️ Visual Report**: Creates an interactive HTML dashboard (`index.html`) with card images, prices, and stats.
*   **💰 Profit/Loss Calculator**: See exactly how much money you've made (or lost) on each card.
*   **🚨 Discord Alerts**: Get notified automatically when your collection value spikes.
*   **📊 Excel Export**: Saves a detailed spreadsheet (`MY_COLLECTION_PRICES.xlsx`) with all your data.

## Setup

1.  **Install Python**: Ensure you have Python installed.
2.  **Install Dependencies**:
    ```bash
    pip install matplotlib openpyxl
    ```

## Usage

### 1. Add Your Cards
There are two text files in this folder. Open them and list your cards:

*   **mtg_cards.txt**: List your Magic cards here.
*   **ygo_cards.txt**: List your Yu-Gi-Oh! cards here.

**Example:**
```text
Blue-Eyes White Dragon
Dark Magician | 5.00
3x Pot of Greed
```
*(Note: You can optionally add `| Price` to track how much you bought it for!)*

### 2. Configure Alerts (Optional)
To get Discord notifications:
1.  Open `price_tracker.py` in a text editor.
2.  Find the line: `DISCORD_WEBHOOK_URL = ""`
3.  Paste your Discord Webhook URL inside the quotes.

### 3. Run the Tracker
Double-click `price_tracker.py` or run it from the terminal:
```bash
python price_tracker.py
```

## Output

*   **index.html**: Open this in your browser to see your **Visual Report**.
*   **MY_COLLECTION_PRICES.xlsx**: The detailed spreadsheet of your collection.
*   **price_history.csv**: The raw data log of your collection's value over time.
*   **last_run_prices.json**: Stores the prices from the last run to calculate trends.
*   **history_graph.png**: The image file of your value graph.

## API Usage

*   **Magic: The Gathering**: Uses [Scryfall API](https://scryfall.com/docs/api).
*   **Yu-Gi-Oh!**: Uses [YGOPRODeck API](https://db.ygoprodeck.com/api-guide/).

## How it was Built
This tool was developed using a "Human-in-the-Loop" workflow leveraging **Google Antigravity** and **Gemini 3 Pro**.

* **AI Role:** Accelerated development by implementing data visualization (`matplotlib`), HTML report generation, and API integration for multiple games.
* **Developer Role:** Directed feature roadmap, designed the Profit/Loss logic, and ensured the tool remains user-friendly and robust.
