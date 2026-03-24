# daily-status

Collects your daily work status from GitHub PRs and Jira tickets, then optionally posts it to a Slack thread.

**What it does:**
- Fetches PRs you created/updated/merged in the last N hours from a GitHub org
- Extracts Jira ticket IDs from PR titles
- Queries Jira for In Progress and recently Done tickets
- Merges and deduplicates tickets from both sources
- Prints a summary to stdout
- Optionally posts to a Slack thread (with `--slack`)

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [GitHub CLI (`gh`)](https://cli.github.com/) — authenticated via `gh auth login`
- Jira API token ([create one here](https://id.atlassian.com/manage-profile/security/api-tokens))
- Slack Bot Token (only for `--slack`) with `channels:history` and `chat:write` scopes

### Install

```bash
git clone <repo-url> && cd daily-status
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Required | Description |
|---|---|---|
| `INFISICAL_TOKEN` | Yes | Infisical service token or machine identity access token |
| `INFISICAL_PROJECT_ID` | Yes | Project ID to read secrets from |
| `INFISICAL_ENV` | No | Secret environment to read from (default: `dev`) |
| `INFISICAL_PATH` | No | Secret path/folder to read from (default: `/`) |
| `INFISICAL_API_URL` | For self-hosted | Base API URL for your Infisical instance |
| `GITHUB_ORG` | Yes | GitHub org to search PRs in |
| `JIRA_BASE_URL` | Yes | e.g. `https://yourcompany.atlassian.net` |
| `JIRA_USER_EMAIL` | Yes | Your Jira account email |
| `JIRA_API_TOKEN` | Yes | Jira API token |
| `SLACK_BOT_TOKEN` | For `--slack` | Slack bot token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | For `--slack` | Channel ID to find the thread in |
| `SLACK_THREAD_KEYWORD` | No | Text to match the thread (default: `Daily Status Updates`) |
| `LOOKBACK_HOURS` | No | Hours to look back (default: `14`) |

## Usage

### Print status to terminal

```bash
source .env
uv run daily_status.py
```

### Post to Slack

```bash
source .env
uv run daily_status.py --slack
```

### Cron (run daily at 5 AM)

```bash
# crontab -e
0 5 * * 1-5 cd /path/to/daily-status && source .env && uv run daily_status.py --slack >> /tmp/daily_status.log 2>&1
```

## Docker

### Build

```bash
docker build -t daily-status .
```

### Run (print only)

```bash
docker run --rm \
  --env-file .env \
  daily-status
```

### Run (post to Slack)

```bash
docker run --rm \
  --env-file .env \
  daily-status --slack
```

The container starts with `infisical run`, then launches `uv run daily_status.py`.
Store the app secrets in Infisical and pass only the Infisical auth/config values into the container.

## Output example

```
PRs created/updated/merged in the last 14 hours (3 found):

  [MERGED] repo-a#42: [TM-1234] Add feature X
    https://github.com/Org/repo-a/pull/42  (updated 2h 10m ago)

  [MERGED] repo-b#99: [TM-5678] Fix bug Y
    https://github.com/Org/repo-b/pull/99  (updated 1h 5m ago)

  [OPEN] repo-c#7: [TM-9999] Refactor Z
    https://github.com/Org/repo-c/pull/7  (updated 0h 30m ago)

In Progress (1):
  TM-9999: Refactor Z
    https://yourcompany.atlassian.net/browse/TM-9999
Done (2):
  TM-1234: Add feature X
    https://yourcompany.atlassian.net/browse/TM-1234
  TM-5678: Fix bug Y
    https://yourcompany.atlassian.net/browse/TM-5678
```

Slack message format:

> **In Progress:**
> - [TM-9999: Refactor Z](https://yourcompany.atlassian.net/browse/TM-9999)
>
> **Done:**
> - [TM-1234: Add feature X](https://yourcompany.atlassian.net/browse/TM-1234)
> - [TM-5678: Fix bug Y](https://yourcompany.atlassian.net/browse/TM-5678)
