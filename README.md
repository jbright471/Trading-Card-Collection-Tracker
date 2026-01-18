# 🃏 Multi-Game Card Tracker

A powerful Python dashboard to track the value of your **Magic: The Gathering** and **Yu-Gi-Oh!** collections.

Combine your TCG hobbies into one sleek report. This tool pulls real-time data to track prices, visualize trends, and calculate your total portfolio value.

## ✨ Features

*   **Two Games, One Tracker**: Seamlessly combines MTG and Yu-Gi-Oh! into a single unified report.
*   **📈 Price History**: Automatically generates a line graph to visualize your total collection value over time.
*   **🖼️ Visual Dashboard**: Generates a clean `index.html` report with high-res card art, current prices, and stats.
*   **⭐️ Holo-Foil Effect**: Add `(Foil)` to card names to see a stunning interactive 3D holographic effect on the card in the report.
*   **💰 Profit/Loss Calculator**: Input your buy price to see exactly how much you've made (or lost) on each card.
*   **🚨 Discord Alerts**: Get automatic pings via Webhook when your collection value spikes beyond a threshold.
*   **📊 Excel Export**: Auto-saves a detailed `MY_COLLECTION_PRICES.xlsx` spreadsheet for your records.

## 🚀 Setup

### 1. Prerequisites
Ensure you have Python installed on your machine.

### 2. Install Dependencies
Run the following command in your terminal to install the required libraries:
```bash
pip install matplotlib openpyxl
```

## 📖 Usage

### 1. Add Your Cards
Open the text files in the project folder and list your cards. You can simply list the name, or add a pipe `|` to track your purchase price.

**mtg_cards.txt** or **ygo_cards.txt**:
```text
Blue-Eyes White Dragon
Dark Magician | 5.00
3x Pot of Greed
Black Lotus (Foil)
```
*   **Quantity**: Use `3x Name` to track multiple copies.
*   **Buy Price**: Use `| 5.00` to track cost basis (optional).
*   **Foil**: Add `(Foil)` to enable the visual holographic effect (optional).

### 2. Configure Alerts (Optional)
To receive notifications on Discord:
1.  Open `price_tracker.py` in a text editor.
2.  Find the variable `DISCORD_WEBHOOK_URL`.
3.  Paste your Discord Webhook URL inside the quotes.

### 3. Run the Tracker
**Option A: The Easy Way (Recommended)**
Simply double-click the `Run Price Tracker.bat` file in the folder. A window will open, run your update, and stay open so you can read the results.

**Option B: Command Line**
Execute the script from your terminal:
```bash
python price_tracker.py
```

## 📂 Output Files

| File | Description |
| :--- | :--- |
| `index.html` | 🌟 **Start Here**. Your interactive visual report dashboard. |
| `MY_COLLECTION_PRICES.xlsx` | Detailed spreadsheet of your entire collection. |
| `price_history.csv` | Raw data log of value over time (used for the graph). |
| `history_graph.png` | The generated image of your value graph. |

## ☁️ Pushing to GitHub
To save your changes and card updates to the cloud, user the following commands in your terminal (or Command Prompt):

```bash
# 1. Check which files have changed
git status

# 2. Add all changes to the staging area
git add .

# 3. Commit the changes with a message (describe what you did)
git commit -m "Update card list and prices"

# 4. Push to GitHub
git push
```

## 🛠️ Built With
This project uses the following robust APIs:
*   **Magic: The Gathering**: Scryfall API
*   **Yu-Gi-Oh!**: YGOPRODeck API

## 🤖 Human-in-the-Loop Development
This tool was developed using an iterative AI workflow leveraging Google Antigravity and Gemini.

*   **AI Role**: Accelerated development by implementing data visualization (matplotlib), HTML report generation, and multi-game API integration.
*   **Developer Role**: Directed feature roadmap, designed the Profit/Loss logic, and ensured the tool remains user-friendly and robust.
