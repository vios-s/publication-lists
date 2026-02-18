# Publication Lists

Automated publication fetching system for research group websites. Fetches publications from OpenAlex, deduplicates entries, applies collaborator filters, and generates HTML output.

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

Output: `output/{group}_publications.html` for each configured group.

**Usage:**
```bash
python generate_lists.py                          # All groups, all years
python generate_lists.py --from-year 2020         # Recent publications only
python generate_lists.py --group VIOS             # Specific group
python generate_lists.py --group VIOS --group CHAI --from-year 2020
```

## Configuration

### people.yaml

Defines groups and members:

```yaml
groups:
  VIOS:
    required_collaborators:
      - "Principal Investigator"  # Papers need this collaborator
  CHAI:
    required_collaborators: []    # No filtering

members:
  - name: "Researcher Name"
    groups:
      - CHAI
      - VIOS  # Can belong to multiple groups
    orcid: "0000-0000-0000-0000"  # Recommended for accuracy
    institution: "University Name"  # Optional, helps ORCID lookup
    required_collaborators:  # Optional, additional per-member requirements
      - "Specific Advisor"
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
  - title: "Your Paper Title"
    authors:
      - "First Author"
      - "Second Author"
    year: 2024
    groups:
      - VIOS
    venue: "Conference Name"  # Optional
    doi: "10.1234/example"    # Optional
    url: "https://..."        # Optional, used if no DOI
```

Required fields: `title`, `authors`, `year`, `groups`. All other fields are optional.

### excluded_dois.yaml

Exclude incorrectly attributed publications:

```yaml
excluded_dois:
  - "10.1234/wrong.paper"
  - "10.5678/another.wrong"
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
  - name: "Member Name"
    groups:
      - NewGroup
```

3. Run the script - done! Output will be `output/newgroup_publications.html`

### Automation

Schedule with cron:
```bash
# Weekly updates - fetch only recent publications
0 2 * * 1 cd /path/to/publication-lists && python generate_lists.py --from-year 2020
```
