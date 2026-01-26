#!/usr/bin/env python3
"""
Paper Aggregation System for CHAI and VIOS websites
Fetches publications from multiple sources, deduplicates,
and generates website-ready output.
"""

import json
import os
import yaml
import requests
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
import time


class PaperFetcher:
    """Fetches and processes academic publications from multiple sources."""

    def __init__(self, people_file: str, output_dir: str = 'output'):
        self.people_file = people_file
        self.output_dir = output_dir
        self.people = []
        self.group_config = {}  # Group-level configuration
        self.publications = {}  # DOI -> publication data

        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)

    def load_config(self):
        """Load people configuration."""
        print("Loading configuration...")

        # Load people and groups
        with open(self.people_file, 'r') as f:
            config = yaml.safe_load(f)
            self.people = config.get('members', [])
            self.group_config = config.get('groups', {})
        print(f"  Loaded {len(self.people)} group members")
        print(f"  Loaded configuration for {len(self.group_config)} groups")

    def fetch_from_openalex(self, author_name: str,
                            orcid: Optional[str] = None,
                            openalex_id: Optional[str] = None) -> List[Dict]:
        """Fetch publications from OpenAlex API."""
        papers = []

        try:
            # Build query
            if orcid:
                # ORCID is most reliable
                url = (
                    f"https://api.openalex.org/works?filter="
                    f"authorships.author.orcid:{orcid}"
                )
                strategy = f"ORCID: {orcid}"
            elif openalex_id:
                url = (
                    f"https://api.openalex.org/works?filter="
                    f"authorships.author.id:{openalex_id}"
                )
                strategy = f"OpenAlex ID: {openalex_id}"
            else:
                # Fall back to name search (less reliable)
                url = (
                    f"https://api.openalex.org/works?filter="
                    f"raw_author_name.search:{author_name}"
                )
                strategy = "name search (fallback)"

            url += "&per-page=200&mailto=your-email@domain.com"  # Polite pool

            print(f"    Querying OpenAlex for {author_name} using {strategy}...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for work in data.get('results', []):
                paper = self._parse_openalex_work(work)
                if paper:
                    papers.append(paper)

            print(f"    Found {len(papers)} papers from OpenAlex")

        except Exception as e:
            print(f"    Warning: OpenAlex fetch failed for {author_name}: {e}")

        return papers

    def _parse_openalex_work(self, work: Dict) -> Optional[Dict]:
        """Parse OpenAlex work into standardized format."""
        try:
            # Extract DOI (handle None case)
            doi = (work.get('doi') or '').replace('https://doi.org/', '')

            # Extract basic info
            paper = {
                'doi': doi or None,
                'title': work.get('title', ''),
                'year': work.get('publication_year'),
                'authors': [author.get('author', {}).get('display_name', '')
                            for author in work.get('authorships', [])],
                'venue': self._extract_venue(work),
                'url': work.get('doi') or work.get('id', ''),
                'citation_count': work.get('cited_by_count', 0),
                'source': 'openalex',
                'raw_data': work
            }

            return paper if paper['title'] else None

        except Exception as e:
            print(f"    Warning: Failed to parse OpenAlex work: {e}")
            return None

    def _extract_venue(self, work: Dict) -> str:
        """Extract venue/publication name from OpenAlex work."""
        # Try primary location
        primary = work.get('primary_location', {})
        if primary:
            source = primary.get('source', {})
            if source and source.get('display_name'):
                return source['display_name']

        # Try best OA location
        best_oa = work.get('best_oa_location', {})
        if best_oa:
            source = best_oa.get('source', {})
            if source and source.get('display_name'):
                return source['display_name']

        # Try host venue (older API format)
        host = work.get('host_venue', {})
        if host and host.get('display_name'):
            return host['display_name']

        return 'Unknown Venue'

    def find_orcid_for_person(self, author_name: str,
                              institution_name: Optional[str] = None
                              ) -> Optional[str]:
        """Try to find ORCID for a person using ORCID API."""
        try:
            print(f"    Attempting to find ORCID for {author_name}...")

            # Parse name into components (simple approach)
            name_parts = author_name.strip().split()
            if len(name_parts) < 2:
                print("    Cannot parse name into first/last name")
                return None

            given_name = name_parts[0]
            family_name = ' '.join(name_parts[1:])

            # Build ORCID API query
            query_parts = [
                f'given-names:{given_name}',
                f'family-name:{family_name}'
            ]

            if institution_name:
                query_parts.append(f'affiliation-org-name:"{institution_name}"')

            query = '+AND+'.join(query_parts)
            url = f"https://pub.orcid.org/v3.0/search/?q={query}&rows=5"

            headers = {
                'Accept': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = data.get('result', [])

            if not results:
                print(f"    No ORCID found for {author_name}")
                return None

            # If we have exactly one match, use it
            if len(results) == 1:
                orcid_uri = results[0].get('orcid-identifier', {}).get('uri', '')
                orcid = orcid_uri.replace('https://orcid.org/', '')
                if orcid:
                    print(f"    Found ORCID: {orcid}")
                    return orcid

            # Multiple matches - show options and pick first one
            elif len(results) > 1:
                print(f"    Found {len(results)} possible matches:")
                for i, result in enumerate(results[:3], 1):  # Show top 3
                    orcid_uri = result.get('orcid-identifier', {}).get('uri', '')
                    orcid = orcid_uri.replace('https://orcid.org/', '')
                    print(f"      {i}. ORCID: {orcid}")

                # Pick the first match (sorted by relevance)
                first_match = results[0]
                orcid_uri = first_match.get('orcid-identifier', {}).get('uri', '')
                orcid = orcid_uri.replace('https://orcid.org/', '')
                if orcid:
                    print(f"    Using first match (most relevant): {orcid}")
                    return orcid

        except Exception as e:
            print(f"    Warning: ORCID lookup failed: {e}")

        return None

    def fetch_all_publications(self):
        """Fetch publications for all group members."""
        print("\nFetching publications...")

        for person in self.people:
            name = person.get('name')
            orcid = person.get('orcid')
            openalex_id = person.get('openalex_id')
            institution = person.get('institution')  # Optional
            groups = person.get('groups', [])

            print(f"\n  Processing: {name} ({', '.join(groups)})")

            # Try to find ORCID if not provided
            if not orcid and not openalex_id:
                print("    No ORCID or OpenAlex ID provided, attempting lookup...")
                orcid = self.find_orcid_for_person(name, institution)

                if orcid:
                    print(f"    ⚠️  Consider adding this ORCID to people.yaml: {orcid}")
                else:
                    print("    ⚠️  Falling back to name search (less reliable)")

            # Fetch from OpenAlex
            papers = self.fetch_from_openalex(name, orcid, openalex_id)

            # Add group tags to papers
            for paper in papers:
                if 'groups' not in paper:
                    paper['groups'] = []
                paper['groups'].extend(groups)
                paper['groups'] = list(set(paper['groups']))  # Deduplicate

            # Merge into main collection
            self._merge_papers(papers)

            # Be polite to APIs
            time.sleep(0.5)

        print(f"\nTotal unique publications collected: {len(self.publications)}")

    def _merge_papers(self, papers: List[Dict]):
        """Merge papers into main collection, deduplicating by DOI."""
        for paper in papers:
            doi = paper.get('doi')

            if doi and doi in self.publications:
                # Merge groups
                existing = self.publications[doi]
                existing['groups'] = list(set(existing['groups'] + paper['groups']))

                # Keep paper with more complete data
                if len(str(paper)) > len(str(existing)):
                    paper['groups'] = existing['groups']
                    self.publications[doi] = paper
            elif doi:
                self.publications[doi] = paper
            else:
                # No DOI - use title+year as fallback key
                key = f"{paper.get('title', '')}_{paper.get('year', '')}"
                if key not in self.publications:
                    self.publications[key] = paper
                else:
                    # Merge groups
                    existing = self.publications[key]
                    existing['groups'] = list(set(existing['groups'] + paper['groups']))

    def filter_group_collaborators(self):
        """Filter papers by group-specific collaborator requirements."""
        print("\nApplying group collaborator filters...")

        # Track removals per group
        group_removals = {}
        removed_completely = []

        # Process each group's collaborator requirements
        for group_name, group_settings in self.group_config.items():
            required_collabs = group_settings.get('required_collaborators', [])

            # Skip if no collaborator requirements for this group
            if not required_collabs:
                continue

            removed_count = 0

            for key, paper in list(self.publications.items()):
                groups = paper.get('groups', [])

                # Only check papers tagged with this group
                if group_name in groups:
                    authors = paper.get('authors', [])

                    # Check if any required collaborator is in the author list
                    has_collaborator = any(
                        collab in authors for collab in required_collabs
                    )

                    if not has_collaborator:
                        # Remove group tag
                        paper['groups'] = [g for g in groups if g != group_name]
                        removed_count += 1

                        # If paper has no other groups, remove it completely
                        if not paper['groups']:
                            removed_completely.append(key)
                            del self.publications[key]

            if removed_count > 0:
                group_removals[group_name] = removed_count

        # Report results
        if group_removals:
            for group_name, count in group_removals.items():
                print(
                    f"  {group_name}: Removed tag from {count} papers "
                    f"(no required collaborator)"
                )
        if removed_completely:
            print(
                f"  Removed {len(removed_completely)} papers completely "
                f"(no remaining groups)"
            )
        if not group_removals and not removed_completely:
            print("  No papers filtered (no groups have collaborator requirements)")

    def generate_publications_json(self):
        """Generate canonical publications.json file."""
        print("\nGenerating publications.json...")

        # Sort by year (descending), then by title
        sorted_pubs = sorted(
            self.publications.values(),
            key=lambda p: (-(p.get('year') or 0), p.get('title', ''))
        )

        output_file = os.path.join(self.output_dir, 'publications.json')
        with open(output_file, 'w') as f:
            json.dump(sorted_pubs, f, indent=2)

        print(f"  Wrote {len(sorted_pubs)} publications to {output_file}")

    def generate_html_outputs(self):
        """Generate HTML snippets for CHAI and VIOS websites."""
        print("\nGenerating HTML outputs...")

        # Filter publications by group
        chai_pubs = [
            p for p in self.publications.values()
            if 'CHAI' in p.get('groups', [])
        ]
        vios_pubs = [
            p for p in self.publications.values()
            if 'VIOS' in p.get('groups', [])
        ]

        # Sort by year descending
        chai_pubs.sort(key=lambda p: (-(p.get('year') or 0), p.get('title', '')))
        vios_pubs.sort(key=lambda p: (-(p.get('year') or 0), p.get('title', '')))

        # Generate CHAI HTML
        chai_file = os.path.join(self.output_dir, 'chai_publications.html')
        self._generate_html_file(chai_file, chai_pubs, 'CHAI')

        # Generate VIOS HTML
        vios_file = os.path.join(self.output_dir, 'vios_publications.html')
        self._generate_html_file(vios_file, vios_pubs, 'VIOS')

    def _generate_html_file(self, filename: str,
                            publications: List[Dict], group: str):
        """Generate HTML file for a specific group."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{group} Publications</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont,
                         'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .publication {{
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }}
        .publication:last-child {{
            border-bottom: none;
        }}
        .title {{
            font-size: 1.1em;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 8px;
        }}
        .title a {{
            color: #2c3e50;
            text-decoration: none;
        }}
        .title a:hover {{
            color: #3498db;
            text-decoration: underline;
        }}
        .authors {{
            color: #555;
            margin-bottom: 5px;
        }}
        .venue {{
            color: #666;
            font-style: italic;
            margin-bottom: 5px;
        }}
        .meta {{
            color: #888;
            font-size: 0.9em;
        }}
        .year-section {{
            margin-top: 40px;
        }}
        .year-header {{
            font-size: 1.5em;
            font-weight: 700;
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .group-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            margin-left: 10px;
            background: #ecf0f1;
            color: #555;
        }}
    </style>
</head>
<body>
    <h1>{group} Publications</h1>
    <p>Last updated: {datetime.now().strftime('%B %d, %Y')}</p>
    <p>Total publications: {len(publications)}</p>
"""

        # Group by year
        by_year = defaultdict(list)
        for pub in publications:
            year = pub.get('year', 'Unknown')
            by_year[year].append(pub)

        # Generate sections by year
        for year in sorted(by_year.keys(), reverse=True):
            html += '\n    <div class="year-section">\n'
            html += f'        <h2 class="year-header">{year}</h2>\n'

            for pub in by_year[year]:
                title = pub.get('title', 'Untitled')
                authors = ', '.join(pub.get('authors', []))
                venue = pub.get('venue', 'Unknown Venue')
                url = pub.get('url', '')
                doi = pub.get('doi', '')
                groups = pub.get('groups', [])

                html += '        <div class="publication">\n'

                # Title with link
                if url:
                    html += (
                        f'            <div class="title"><a href="{url}" '
                        f'target="_blank">{title}</a>'
                    )
                else:
                    html += f'            <div class="title">{title}'

                # Show both groups if paper appears in both
                if len(groups) > 1:
                    for g in sorted(groups):
                        html += f'<span class="group-badge">{g}</span>'

                html += '</div>\n'

                # Authors
                if authors:
                    html += f'            <div class="authors">{authors}</div>\n'

                # Venue
                html += f'            <div class="venue">{venue}</div>\n'

                # Metadata
                meta_parts = []
                if doi:
                    meta_parts.append(f'DOI: {doi}')
                if pub.get('citation_count'):
                    meta_parts.append(f'Citations: {pub["citation_count"]}')

                if meta_parts:
                    html += (
                        f'            <div class="meta">{" | ".join(meta_parts)}'
                        f'</div>\n'
                    )

                html += '        </div>\n'

            html += '    </div>\n'

        html += """
</body>
</html>
"""

        with open(filename, 'w') as f:
            f.write(html)

        print(f"  Wrote {len(publications)} publications to {filename}")

    def run(self):
        """Run the complete pipeline."""
        print("=" * 60)
        print("Paper Aggregation System")
        print("=" * 60)

        self.load_config()
        self.fetch_all_publications()
        self.filter_group_collaborators()
        self.generate_publications_json()
        self.generate_html_outputs()

        print("\n" + "=" * 60)
        print(f"Done! Generated files in '{self.output_dir}/' directory:")
        print("  - publications.json (canonical data)")
        print("  - chai_publications.html")
        print("  - vios_publications.html")
        print("=" * 60)


def main():
    """Main entry point."""
    fetcher = PaperFetcher('people.yaml')
    fetcher.run()


if __name__ == '__main__':
    main()
