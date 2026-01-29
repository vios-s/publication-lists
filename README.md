# Publication Lists

Automated publication fetching system for research group websites.

## Overview

This tool fetches publications for group members from academic APIs (OpenAlex), deduplicates them, applies group-specific collaborator filters, and generates HTML snippets for group websites.

## Setup

1. Create and activate a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables (optional but recommended):
```bash
# Copy the example .env file and update it
cp .env.example .env
```

4. Configure `people.yaml`:
   - **Group members**:
     - Add all group members (from any research group)
     - Include ORCID IDs when available (most reliable)
     - Optionally include institution names to help with ORCID lookup
     - Script will automatically attempt ORCID lookup for members without ORCID
   - **Group-level settings**:
     - Configure collaborator requirements (e.g., VIOS requires specific co-authors)
     - Add new groups easily - just add them to the `groups` section

## Usage

Run the script:

```bash
# Fetch all publications for all groups (default)
python generate_lists.py

# Fetch only publications from a specific year onwards
python generate_lists.py --from-year 2020

# Fetch publications for a specific group only
python generate_lists.py --group VIOS

# Fetch for multiple specific groups
python generate_lists.py --group VIOS --group CHAI

# Combine options
python generate_lists.py --group CHAI --from-year 2020
```

This will generate files in the `output/` directory:
- `publications.json` - Canonical dataset (single source of truth)
- `{group}_publications.html` - HTML snippet for each configured group (e.g., `chai_publications.html`, `vios_publications.html`)

### Options

- `--from-year YEAR`: Fetch only publications from the specified year onwards (e.g., `--from-year 2020`). Useful for periodic updates to reduce API load and runtime, or to focus on recent work.
- `--group GROUP`: Run only for a specific group. Can be repeated for multiple groups (e.g., `--group VIOS --group CHAI`). Useful when you only need to update one group's publications.

## Adding a New Group

Adding a new research group is simple:

1. **Add group configuration** to `people.yaml`:
   ```yaml
   groups:
     VIOS:
       required_collaborators: []
     CHAI:
       required_collaborators: []
     NewGroup:  # Your new group
       required_collaborators:
         - "Principal Investigator Name"  # or empty list [] for no requirements
   ```

2. **Add members** to the new group:
   ```yaml
   members:
     - name: "Researcher Name"
       groups:
         - NewGroup
       orcid: "0000-0000-0000-0000"
   ```

3. **Run the script** - that's it! The script will automatically:
   - Fetch publications for all NewGroup members
   - Apply collaborator filters (if configured)
   - Generate `newgroup_publications.html` output file

The system is fully dynamic - you can add as many groups as needed without touching the code.

## Configuration

### Environment Variables (.env)

Create a `.env` file (copy from `.env.example`) to configure:

```bash
# OpenAlex polite pool - Recommended for better performance
OPENALEX_EMAIL=your-email@domain.com
```

### people.yaml Structure

The `people.yaml` file contains two main sections:

```yaml
groups:
  VIOS:
    required_collaborators:
      - "Sotirios A. Tsaftaris"
      # Additional collaborators...
  CHAI:
    required_collaborators: []

members:
  - name: "Researcher Name"
    groups:
      - CHAI
    orcid: "0000-0000-0000-0000"  # Recommended
    # Optional fields:
    institution: "University Name"
    openalex_id: "a1234567890"
    required_collaborators:  # Optional: additional requirements beyond group-level
      - "Specific Collaborator Name"
```

**Groups Configuration:**
- Define required collaborators per group
- Papers without a required collaborator won't appear in that group's output
- Empty list `[]` means no group-level requirements

**Members Configuration:**
- `name`: Required
- `groups`: List of groups (CHAI, VIOS, or both)
- `orcid`: Highly recommended for accurate matching
- `institution`: Optional, helps with ORCID lookup if ORCID not provided
- `openalex_id`: Optional alternative to ORCID
- `required_collaborators`: Optional, member-specific collaborator requirements (combined with group-level requirements)

**Collaborator Filtering Logic:**
- Group-level and member-level requirements are combined
- For example, if VIOS requires ["PI Name"] and a member adds ["Advisor Name"], papers must have either collaborator
- This allows flexible filtering where some members in a group have additional requirements beyond the group baseline

## Workflow

1. **First time setup**: Add all group members to `people.yaml`
2. **Run script**: Execute `python generate_lists.py`
3. **Review output**: Check console for ORCID suggestions and filtering results
4. **Update config**: Add suggested ORCIDs to `people.yaml` for faster future runs
5. **Update websites**: Use the HTML snippets in your group websites

## Scheduling (Optional)

To automate updates, add to crontab:

```bash
# Run every Monday at 2 AM - fetch all publications
0 2 * * 1 cd /path/to/publication-lists && python generate_lists.py

# Or fetch only publications from 2020 onwards for faster updates
0 2 * * 1 cd /path/to/publication-lists && python generate_lists.py --from-year 2020

# Or fetch for specific groups only
0 2 * * 1 cd /path/to/publication-lists && python generate_lists.py --group VIOS --from-year 2020
```
