# WAF Category Classifier

A tool to help scrum teams correctly classify JIRA stories into WAF (Work Alignment Framework) categories using Claude AI.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   ```

3. Run the app:
   ```bash
   python app.py
   ```

4. Open http://localhost:5000 in your browser.

## Usage

1. **Upload WAF Definitions** — Upload your WAF category definitions file (CSV, Excel, JSON, or text) in the sidebar.
2. **Upload Ground Truth** — Upload previously classified stories as training examples to improve accuracy.
3. **Classify Stories** — Paste a JIRA story in the chat to get a WAF category recommendation.
4. **Batch Mode** — Switch to batch mode to classify multiple stories at once.

## File Formats

### WAF Definitions
Any tabular or text file with your WAF categories and their definitions.

### Ground Truth (Training Examples)
CSV or Excel with columns: Story Title, Description, WAF Color, WAF Category, WAF Sub-Category

### JIRA Stories
Paste directly or use batch mode with pipe-separated format:
```
Story Title | Description | Current WAF Tag
```
