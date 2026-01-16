# Multi-Game Card Tracker

A simple tool to track the value of your **Magic: The Gathering** and **Yu-Gi-Oh!** collections.

## How to Use

### 1. Add Your Cards
There are two text files in this folder. Open them and list your cards:

*   **mtg_cards.txt**: List your Magic cards here.
*   **ygo_cards.txt**: List your Yu-Gi-Oh! cards here.

**Example:**
```text
Blue-Eyes White Dragon
Dark Magician | 5.00
Dark Magician | 5.00
3x Pot of Greed
Black Lotus (Foil)
```
*(Note: You can optionally add `| Price` to track how much you bought it for!)*
*(Note: Add `(Foil)` to see a cool holographic effect on the card!)*

### 2. Run the Tracker
Double-click the **`price_tracker.py`** file (or run it from a terminal).

### 3. See Your Collection!
*   **Visual Report**: Open **`index.html`** to see a beautiful webpage with images of all your cards.
*   **Spreadsheet**: Open **`MY_COLLECTION_PRICES.xlsx`** for a detailed Excel list.

## Features
*   **Two Games, One Tracker**: Combines MTG and YGO into one report.
*   **Visual Dashboard**: See your collection with card art.
*   **Price History**: Tracks your total value over time.
*   **Profit/Loss**: See if you made money on your cards (Green = Profit, Red = Loss).

## Setup (One-time)
If you are setting this up on a new computer, you need Python installed. Then run:
```bash
pip install matplotlib openpyxl
```
