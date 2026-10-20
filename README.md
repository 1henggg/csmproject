# Semiconductor Supply Chain Dashboard

A beginner-friendly, interactive Streamlit dashboard built from the existing Semiconductor SCM analysis.

## Files

- `app.py` — dashboard code (KPI cards, demand-vs-forecast trend, warehouse stockout-flag rate, ABC class chart, inventory status table, filters)
- `requirements.txt` — Python dependencies for deployment
- `.streamlit/config.toml` — visual theme
- `supply_chain_dataset1.csv` — add your existing dataset to this same folder/repository root

## Run locally (Mac)

1. Install Python 3 if needed.
2. In Terminal, `cd` into this folder.
3. Create and activate a virtual environment (recommended):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Put `supply_chain_dataset1.csv` in the same folder as `app.py`.
6. Start the app:

   ```bash
   python -m streamlit run app.py
   ```

7. Your browser should open a local address, normally `http://localhost:8501`.

## Publish a shareable website

1. In your GitHub repository, keep `supply_chain_dataset1.csv` in the repository root. Add `app.py`, `requirements.txt`, and the `.streamlit` folder to the same root. Do not commit private or sensitive data; this sample dataset will be publicly accessible if the repository/app is public.
2. Open <https://share.streamlit.io/> and sign in with GitHub.
3. Choose **Create app** and select your repository, branch (usually `main`), and entrypoint file `app.py`.
4. Optionally choose a memorable app subdomain, then click **Deploy**.
5. When deployment completes, copy the `*.streamlit.app` URL and test it in a private/incognito browser window.

The app automatically reads the CSV beside `app.py`; if that file is absent, it shows an upload control for testing. For a portfolio link, commit the dataset to the repository so viewers do not need to upload it themselves.

## Important notes

- A public GitHub repository and public Streamlit app make the source and dataset publicly accessible. Use only data you are allowed to share.
- `Stockout Flag Rate` uses the dataset's existing flag; verify the original field definition before describing it as an actual stockout probability.
- Forecast accuracy and ABC boundaries are project-defined analytical choices. Explain their definitions when presenting the project.
