# Get DataVouch running locally

The local viewer lets you explore sample results without a Google Cloud account, credentials or cloud charges. You can review reports and create a BigQuery experiment plan in the browser; collecting evidence still uses the CLI. Commands below start from a terminal. Keep the server terminal open while using the browser.

## 1. Get the source

Install Git and Python 3.15.2 before continuing. Check `git --version` and `python3.15 --version`. On Windows use `py -3.15 --version`. Other Python minor versions are unsupported. If a command is missing, install the prerequisite before proceeding.

The repository is private during development, so your GitHub account must have access. If you already have a checkout, open a terminal in that folder and skip cloning.

```sh
git clone https://github.com/CloudOpsFoundry/datavouch.git
cd datavouch
```

## 2. Install the application

On macOS or Linux:

```sh
python3.15 -m venv .venv
.venv/bin/python -m pip install ".[web]"
.venv/bin/python -m datavouch --version
```

On Windows PowerShell:

```powershell
py -3.15 -m venv .venv
.venv\Scripts\python.exe -m pip install ".[web]"
.venv\Scripts\python.exe -m datavouch --version
```

These commands install from your checkout into an isolated environment. The optional `web` package supplies the browser viewer. Developers should instead follow the [locked development setup](installation.md) to match CI dependencies. Windows commands are provided for setup but have not been validated on a Windows machine.

## 3. Start the viewer

On macOS or Linux:

```sh
.venv/bin/python -m datavouch serve examples/viewer.json --port 8766
```

On Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m datavouch serve examples/viewer.json --port 8766
```

At the prompt, choose a password of 16 to 256 printable ASCII characters. Typing a password does not display characters in the terminal. Open http://127.0.0.1:8766 and sign in with username `datavouch` and your chosen password.

## 4. Check the results

1. Open the Daily summary workload.
2. Open Rewrite verification and confirm PASS.
3. Open Changed result detected and inspect the failed correctness check.
4. Open Financial evidence pending and confirm UNKNOWN. Missing evidence is not a successful result.
5. Download a summary from a detail page and open the JSON file in a text editor.

All bundled examples are synthetic. These checks demonstrate the interface, not production performance or realized savings. See [BigQuery experiments](bigquery-experiments.md) when you are ready to collect authorized evidence. For this development environment, live validation uses only `sandbox-platform-services`, location `eu`.

To create your own plan, first configure [deployment connections](connections.md), then select **New experiment** and follow the [guided planning steps](web.md#plan-a-bigquery-experiment). Validating or downloading a plan does not query Google Cloud.

## 5. Stop, update and restart

Press Ctrl+C in the server terminal to stop it. After changing code, rerun the install command in step 2, then the start command in step 3. The developer setup uses an editable install, so source changes only need a server restart; dependency changes also need `uv sync --locked --all-extras`. Catalog inputs are loaded at startup, so restart after changing evidence files as well. The viewer does not automatically reload or collect new cloud data.

If the address does not open, confirm the terminal still shows a running server and use the exact port printed there. If the port is occupied, choose another port such as `--port 8767` and use that port in the browser. If a browser reuses an old password, open a private browser window and sign in again. Keep the viewer on your own machine; shared team deployment is a future milestone.

## Where to go next

- [Viewer configuration and access controls](web.md)
- [Real BigQuery experiments](bigquery-experiments.md)
- [Contributor setup and CI](development.md)
- [Product objective and UI milestones](product-roadmap.md)
