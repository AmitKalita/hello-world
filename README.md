# RNA Therapeutics / LNP Engineering / Oncology Research Agent

An automated daily digest that searches recent research papers and X
(Twitter) posts for developments in **RNA therapeutics**, **lipid
nanoparticle (LNP) engineering**, and **oncology**, filters/summarizes
them with Claude, and writes the results into a Google Sheet.

It runs on a daily schedule via GitHub Actions — see [How "24/7" actually
works](#how-247-actually-works) below for why that, not an always-on
server, is the right way to run this.

## What it does each run

1. Searches [Europe PMC](https://europepmc.org) (covers PubMed/MEDLINE,
   PubMed Central, and preprint servers like bioRxiv/medRxiv) and
   [Semantic Scholar](https://www.semanticscholar.org) for papers matching
   the keyword lists in `config.yaml`.
2. Searches X for recent posts matching the same keywords (only if
   `X_BEARER_TOKEN` is configured — otherwise this step is skipped).
3. Drops anything already in the sheet (by link/DOI), so nothing gets
   duplicated across runs.
4. Sends what's left to Claude, which decides whether each item is a real,
   on-topic development, tags it (RNA Therapeutics / LNP Engineering /
   Oncology / Cross-cutting), scores its relevance 1–5, and writes a short
   summary.
5. Appends everything scoring at or above `relevance_threshold` to the
   sheet, and logs the run (timestamp, counts, any errors) to a "Run Log"
   tab.

LinkedIn is intentionally **not** included — see
[Known limitations](#known-limitations).

## Google Sheet format

The agent expects (and will auto-create) three tabs:

**Papers**
| Date Added | Pub Date | Title | Authors | Source | Link | Topic | Summary | Relevance Score |
|---|---|---|---|---|---|---|---|---|

**Social Posts (X)**
| Date Added | Platform | Author | Link | Snippet | Summary | Topic | Engagement |
|---|---|---|---|---|---|---|---|

**Run Log**
| Timestamp | Status | New Papers | New Posts | Errors |
|---|---|---|---|---|

## Setup

### 1. Create the Google Sheet and connect it (step-by-step)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and
   create a new project (e.g. name it `rna-research-agent`).
2. In the left menu, go to **APIs & Services → Library**, search for
   **Google Sheets API**, and click **Enable**.
3. Go to **APIs & Services → Credentials → Create Credentials → Service
   account**. Give it any name (e.g. `sheets-writer`), skip the optional
   role/permission steps, and click **Done**.
4. Click into the service account you just created → **Keys** tab →
   **Add Key → Create new key → JSON**. This downloads a `.json` file —
   keep it private, don't commit it anywhere.
5. Open that JSON file in a text editor and copy its *entire* contents
   (it's a single JSON object).
6. Go to [sheets.new](https://sheets.new) to create the spreadsheet the
   agent will write to. Name it whatever you like.
7. From the sheet's URL, copy the **Sheet ID** — the long string between
   `/d/` and `/edit`, e.g. `docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`.
8. In the downloaded JSON file, find the `"client_email"` field (looks
   like `something@your-project.iam.gserviceaccount.com`). In your Google
   Sheet, click **Share** and share it with that email address, with
   **Editor** access.

### 2. Get an Anthropic API key

Create one at [console.anthropic.com](https://console.anthropic.com) →
**API Keys**. This is what powers the relevance filtering and
summarization step.

### 3. (Optional, if you chose to include X) Get an X API Bearer Token

Sign up for a paid developer tier with access to the recent-search
endpoint at [developer.x.com](https://developer.x.com), create a Project
and App, and copy the **Bearer Token**. If you skip this, the agent still
runs fine — it just won't include X posts (leave `X_BEARER_TOKEN` unset).

### 4. Add secrets to this GitHub repository

Go to **Settings → Secrets and variables → Actions → New repository
secret** and add:

| Secret name | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The full contents of the service account JSON file from step 1.5 |
| `GOOGLE_SHEET_ID` | The Sheet ID from step 1.7 |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `X_BEARER_TOKEN` | (Optional) Your X Bearer Token |
| `SEMANTIC_SCHOLAR_API_KEY` | (Optional) Raises Semantic Scholar's rate limit; not required to start |

### 5. Run it

The workflow in `.github/workflows/daily-research.yml` runs automatically
every day at 13:00 UTC. To test it immediately without waiting: go to the
**Actions** tab of this repo → **Daily Research Digest** → **Run
workflow**.

## Customizing what it searches for

Edit `config.yaml` — no code changes needed:
- `topics`: the keyword lists per topic area.
- `relevance_threshold`: raise for fewer/higher-signal results, lower for more.
- `lookback_days`: how far back each run searches.
- `claude_model`: which Claude model does the filtering/summarizing.

## How "24/7" actually works

There's no always-on server here — this repo's environment is ephemeral
and isn't meant to run a persistent process. Instead, GitHub Actions wakes
up on a schedule (currently daily), does a full search-and-summarize pass,
and goes back to sleep. For a research digest, this gives continuous
*coverage* without the cost and maintenance of a server that never turns
off. If you later want more frequent updates, edit the `cron` line in
`.github/workflows/daily-research.yml` (e.g. `0 */6 * * *` for every 6
hours) — just note that more frequent runs mean more Anthropic/X/API
usage and cost.

## Known limitations

- **LinkedIn is not included.** There's no compliant public API for
  searching LinkedIn content, and scraping it violates LinkedIn's Terms
  of Service (real risk of account suspension). If you want LinkedIn
  coverage, the safest path is manually forwarding posts you find
  interesting — this isn't automated in the current build.
- **X coverage depends on your API tier.** The recent-search endpoint only
  covers roughly the last 7 days regardless of `lookback_days`.
- **LNP-engineering coverage may be thinner** than RNA/oncology coverage,
  since some materials-science and chemistry journals are less fully
  indexed in the biomedical databases this agent searches (Europe PMC,
  Semantic Scholar) than in PubMed's core scope.
- **Google Scholar is not used** — it has no public API, and scraping it
  is against its terms.
- Each run costs a small amount in Anthropic API usage (and X API usage,
  if enabled) proportional to how many new items are found and how often
  it runs.
