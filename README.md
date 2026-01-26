# Paper Aggregation System

Automated publication fetching system for CHAI and VIOS group websites.

## Overview

This tool fetches publications for group members from academic APIs (OpenAlex), deduplicates them, applies group-specific collaborator filters, and generates ready-to-use HTML snippets for both websites.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure group members in `people.yaml`:
   - Add all CHAI and VIOS members
   - Include ORCID IDs when available (most reliable)
   - Optionally include institution names to help with ORCID lookup
   - Script will automatically attempt ORCID lookup for members without ORCID
   - Configure group-level collaborator requirements (e.g., VIOS requires specific co-authors)

## Usage

Run the script:
```bash
python fetch_papers.py
```

This will generate files in the `output/` directory:
- `publications.json` - Canonical dataset (single source of truth)
- `chai_publications.html` - HTML snippet for CHAI website
- `vios_publications.html` - HTML snippet for VIOS website

## File Structure

- **people.yaml** - Group member configuration and collaborator requirements
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
5. **Update websites**: Copy HTML snippets to CHAI (Squarespace) and VIOS sites

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
# Run every Monday at 9 AM
0 9 * * 1 cd /path/to/fetch-papers && python fetch_papers.py
```
