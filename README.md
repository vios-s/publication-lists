# Publication Lists

Automated publication fetching system for research group websites. Fetches publications from OpenAlex, deduplicates entries, applies collaborator filters, and generates HTML or YAML output.

## Quick Start

```bash
# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure people.yaml with your group members
# (Optional) Set OPENALEX_EMAIL in .env for better API performance

# Run
python generate_lists.py
```

Output: `output/{group}_publications.html` (or `.yaml`) for each configured group.

**Usage:**

| Command | Description |
|---|---|
| `python generate_lists.py` | All groups, all years (HTML) |
| `python generate_lists.py --format yaml` | All groups, all years (YAML) |
| `python generate_lists.py --from-year 2020` | Recent publications only |
| `python generate_lists.py --group VIOS` | Specific group |
| `python generate_lists.py --group VIOS --group CHAI --from-year 2020` | Multiple groups, recent only |
| `python generate_lists.py --render-only` | Re-render from saved data (no API calls) |
| `python generate_lists.py --render-only --format yaml` | Re-render as YAML from saved data |
| `python generate_lists.py --render-only --group VIOS` | Re-render one group only |
| `python generate_lists.py --data-file path/to/data.yaml --render-only` | Custom data file |

The script works in two stages:
1. **Fetch** — queries OpenAlex APIs, merges with manual publications, applies filters, and saves a canonical data file (`output/publications_data.yaml`).
2. **Render** — reads the data file and generates HTML or YAML output using per-group templates.

Use `--render-only` to skip fetching and re-render instantly from the saved data. This is useful when iterating on templates.
Use `--format yaml` to produce YAML output instead of HTML.

## Configuration

### people.yaml

Defines groups and members:

```yaml
groups:
  VIOS:
    required_collaborators:
      - Principal Investigator  # Papers need this collaborator
  CHAI:
    required_collaborators: []    # No filtering

members:
  - name: Researcher Name
    groups:
      - CHAI
      - VIOS  # Can belong to multiple groups
    orcid: 0000-0000-0000-0000  # Recommended for accuracy
    institution: University Name  # Optional, helps ORCID lookup
    required_collaborators:  # Optional, additional per-member requirements
      - Specific Advisor
```

**Key points:**
- ORCID is highly recommended for accurate matching
- Script auto-attempts ORCID lookup if missing
- Collaborator requirements combine group + member level
- Empty `required_collaborators: []` means no filtering

### manual_publications.yaml

Manually add publications not found in OpenAlex:

```yaml
manual_publications:
  - title: Your Paper Title
    authors:
      - First Author
      - Second Author
    date: "2024-01-01"
    groups:
      - VIOS
    venue: Conference Name  # Optional
    doi: 10.1234/example    # Optional
    url: https://...        # Optional
```

Required fields: `title`, `authors`, `date` (`YYYY-MM-DD`), `groups`. All other fields are optional.

**Note:** Manual publications bypass the collaborator filter. They are always included in the output for their specified groups, regardless of `required_collaborators` settings.

### excluded_dois.yaml

Exclude incorrectly attributed publications:

```yaml
excluded_dois:
  - 10.1234/wrong.paper
  - 10.5678/another.wrong
```

### .env

Optional but recommended for better API performance:

```bash
OPENALEX_EMAIL=your-email@domain.com
```

## Advanced

### Adding a New Group

1. Add to `people.yaml`:
```yaml
groups:
  NewGroup:
    required_collaborators: []  # or add names
```

2. Tag members with the group:
```yaml
members:
  - name: Member Name
    groups:
      - NewGroup
```

3. (Optional) Create a custom template at `templates/newgroup_publications.html` (or `.yaml`). If none exists, the default `templates/publications.html` (or `templates/publications.yaml`) is used.

4. Run the script - done! Output will be `output/newgroup_publications.html` (or `.yaml` with `--format yaml`)

### Templates

Templates live in the `templates/` directory and use [Jinja2](https://jinja.palletsprojects.com/) syntax. The script resolves templates by convention:

**HTML** (default):
- `templates/{group}_publications.html` — used if it exists (e.g., `templates/vios_publications.html`)
- `templates/publications.html` — default fallback

**YAML** (`--format yaml`):
- `templates/{group}_publications.yaml` — used if it exists
- `templates/publications.yaml` — default fallback

### Automation

Schedule with cron:
```bash
# Weekly updates - fetch only recent publications
0 2 * * 1 cd /path/to/publication-lists && python generate_lists.py --from-year 2020
```
