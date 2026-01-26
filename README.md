# Paper Aggregation System

Automated publication fetching system for research group websites.

## Overview

This tool fetches publications for group members from academic APIs (OpenAlex), deduplicates them, applies group-specific collaborator filters, and generates ready-to-use HTML snippets for group websites. The system is **group-agnostic** - easily add new research groups by simply editing the configuration file.

## Setup

1. Create and activate a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows
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
# Fetch all publications (default)
python fetch_papers.py

# Fetch only current year publications (faster, for weekly updates)
python fetch_papers.py --current-year-only
```

This will generate files in the `output/` directory:
- `publications.json` - Canonical dataset (single source of truth)
- `{group}_publications.html` - HTML snippet for each configured group (e.g., `chai_publications.html`, `vios_publications.html`)

### Options

- `--current-year-only`: Fetch only publications from the current year (2026). Useful for weekly updates to reduce API load and runtime.

## Adding a New Group

Adding a new research group is simple - **no code changes required**:

1. **Add group configuration** to `people.yaml`:
   ```yaml
   groups:
     VIOS:
       required_collaborators:
         - "Sotirios A. Tsaftaris"
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
# OpenAlex Polite Pool - Recommended for better performance
OPENALEX_EMAIL=your-email@domain.com
```

**Benefits of setting OPENALEX_EMAIL:**
- Higher rate limits
- Faster response times
- Better service reliability
- No authentication required, just an email address

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
```

**Groups Configuration:**
- Define required collaborators per group
- Papers without a required collaborator won't appear in that group's output

**Members Configuration:**
- `name`: Required
- `groups`: List of groups (CHAI, VIOS, or both)
- `orcid`: Highly recommended for accurate matching
- `institution`: Optional, helps with ORCID lookup if ORCID not provided
- `openalex_id`: Optional alternative to ORCID

## File Structure

- **people.yaml** - Configuration file (members and groups)
- **.env** - Environment-specific settings (email, etc.) - excluded from git
- **.env.example** - Template for .env file
- **fetch_papers.py** - Main script
- **output/** - Generated files directory
  - **publications.json** - Canonical dataset
  - **chai_publications.html** - CHAI website snippet
  - **vios_publications.html** - VIOS website snippet

## Workflow

1. **First time setup**: Add all group members to `people.yaml`
2. **Run script**: Execute `python fetch_papers.py`
3. **Review output**: Check console for ORCID suggestions and filtering results
4. **Update config**: Add suggested ORCIDs to `people.yaml` for faster future runs
5. **Update websites**: Copy HTML snippets to your group websites

## Notes

- OpenAlex API is free and doesn't require authentication
- ORCID API is used for automatic ORCID discovery
- Script is polite to APIs (includes delays between requests)
- Papers appearing in both groups are listed in both outputs with badges
- VIOS papers require at least one specified collaborator
- First run may take a few minutes depending on group size

## Scheduling (Optional)

To automate weekly updates, add to crontab:

```bash
# Run every Monday at 2 AM - fetch all publications
0 2 * * 1 cd /path/to/fetch-papers && python fetch_papers.py

# Or fetch only current year for faster updates
0 2 * * 1 cd /path/to/fetch-papers && python fetch_papers.py --current-year-only
```
