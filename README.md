# Arma Reforger Discord Bot

This bot is designed to integrate with your Arma Reforger server, providing the following functionalities:

- **Display active players on the server**
- **Show server logs in a designated Discord channel**
- **Start and stop the Arma Reforger server directly from Discord**

---

## Installation Instructions

There are two methods to run this bot: using a batch file or by manually running the Python script.

### Method 1: Run using the Batch File

1. Download the bot's files to your system.
2. Double-click on `Start-Bot.bat`.
   - This will automatically install the necessary packages and start the bot.

### Method 2: Run using the Python Script

If you prefer to manually run the bot, follow these steps:

#### 1. Create a Virtual Environment

To ensure that the bot runs with the correct dependencies, it's recommended to use a virtual environment. Run the following commands:

```
python -m venv venv
venv\Scripts\activate    # On Windows
source venv/bin/activate # On macOS/Linux
```

#### 2. Install Required Packages
Once the virtual environment is activated, install the required dependencies:

```
pip install -r requirements.txt
```

#### 3. Launch the Script
After installing the packages, run the bot script:

```
python bot.py
```