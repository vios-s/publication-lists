import argparse
import json
import os
import yaml
import requests
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
import time


class ListGenerator:

    def __init__(self, people_file: str, output_dir: str = "output",
                 polite_pool_email: Optional[str] = None):
        self.people_file = people_file
        self.output_dir = output_dir
        self.people = []
        self.group_config = {}
        self.publications = {}
        self.discovered_orcids = {}

        if polite_pool_email is None:
            polite_pool_email = os.getenv("OPENALEX_EMAIL")
        self.polite_pool_email = polite_pool_email

        os.makedirs(self.output_dir, exist_ok=True)

    def load_config(self):
        print("Loading configuration...")

        with open(self.people_file, "r") as file:
            config = yaml.safe_load(file)
            self.people = config.get("members", [])
            self.group_config = config.get("groups", {})

        print(f"  Loaded {len(self.people)} group members")
        print(f"  Loaded configuration for {len(self.group_config)} groups")
        if self.polite_pool_email:
            print(f"  Using polite pool email: {self.polite_pool_email}")

    def fetch_from_openalex(self, author_name: str,
                            orcid: Optional[str] = None,
                            openalex_id: Optional[str] = None,
                            from_year: Optional[int] = None) -> List[Dict]:
        papers = []

        try:
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

            if from_year:
                url += f",from_publication_date:{from_year}-01-01"

            url += "&per-page=200"
            if self.polite_pool_email:
                url += f"&mailto={self.polite_pool_email}"

            print(f"    Querying OpenAlex for {author_name} using {strategy}...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for work in data.get("results", []):
                paper = self._parse_openalex_work(work)
                if paper:
                    papers.append(paper)

            print(f"    Found {len(papers)} papers from OpenAlex")

        except Exception as e:
            print(f"    Warning: OpenAlex fetch failed for {author_name}: {e}")

        return papers

    def _parse_openalex_work(self, work: Dict) -> Optional[Dict]:
        try:
            doi = (work.get("doi") or "").replace("https://doi.org/", "")

            paper = {
                "doi": doi or None,
                "title": work.get("title", ""),
                "year": work.get("publication_year"),
                "authors": [author.get("author", {}).get("display_name", "")
                            for author in work.get("authorships", [])],
                "venue": self._extract_venue(work),
                "url": work.get("doi") or work.get("id", ""),
                "citation_count": work.get("cited_by_count", 0),
                "source": "openalex",
                "raw_data": work
            }

            return paper if paper["title"] else None

        except Exception as e:
            print(f"    Warning: Failed to parse OpenAlex work: {e}")
            return None

    def _extract_venue(self, work: Dict) -> str:
        # Try primary location
        primary = work.get("primary_location", {})
        if primary:
            source = primary.get("source", {})
            if source and source.get("display_name"):
                return source["display_name"]

        # Try best OA location
        best_oa = work.get("best_oa_location", {})
        if best_oa:
            source = best_oa.get("source", {})
            if source and source.get("display_name"):
                return source["display_name"]

        # Try host venue (older API format)
        host = work.get("host_venue", {})
        if host and host.get("display_name"):
            return host["display_name"]

        return "Unknown Venue"

    def find_orcid_for_person(self, author_name: str,
                              institution_name: Optional[str] = None
                              ) -> Optional[str]:
        try:
            print(f"    Attempting to find ORCID for {author_name}...")

            name_parts = author_name.strip().split()
            if len(name_parts) < 2:
                print("    Cannot parse name into first/last name")
                return None

            given_name = name_parts[0]
            family_name = " ".join(name_parts[1:])

            query_parts = [
                f"given-names:{given_name}",
                f"family-name:{family_name}"
            ]

            if institution_name:
                query_parts.append(f"affiliation-org-name:\"{institution_name}\"")

            query = "+AND+".join(query_parts)
            url = f"https://pub.orcid.org/v3.0/search/?q={query}&rows=5"

            headers = {
                "Accept": "application/json"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = data.get("result", [])

            if not results:
                print(f"    No ORCID found for {author_name}")
                return None

            # If we have exactly one match, use it
            if len(results) == 1:
                orcid_uri = results[0].get("orcid-identifier", {}).get("uri", "")
                orcid = orcid_uri.replace("https://orcid.org/", "")
                if orcid:
                    print(f"    Found ORCID: {orcid}")
                    return orcid

            # Multiple matches - show options and pick first one
            elif len(results) > 1:
                print(f"    Found {len(results)} possible matches:")
                for i, result in enumerate(results[:3], 1):
                    orcid_uri = result.get("orcid-identifier", {}).get("uri", "")
                    orcid = orcid_uri.replace("https://orcid.org/", "")
                    print(f"      {i}. ORCID: {orcid}")

                # Pick the first match (sorted by relevance)
                first_match = results[0]
                orcid_uri = first_match.get("orcid-identifier", {}).get("uri", "")
                orcid = orcid_uri.replace("https://orcid.org/", "")
                if orcid:
                    print(f"    Using first match (most relevant): {orcid}")
                    return orcid

        except Exception as e:
            print(f"    Warning: ORCID lookup failed: {e}")

        return None

    def fetch_all_publications(self, from_year: Optional[int] = None):
        print("\nFetching publications...")
        if from_year:
            print(f"  Filtering to publications from {from_year} onwards")

        for person in self.people:
            name = person.get("name")
            orcid = person.get("orcid")
            openalex_id = person.get("openalex_id")
            institution = person.get("institution")
            groups = person.get("groups", [])

            print(f"\n  Processing: {name} ({", ".join(groups)})")

            # Try to find ORCID if not provided
            if not orcid and not openalex_id:
                print("    No ORCID or OpenAlex ID provided, attempting lookup...")
                orcid = self.find_orcid_for_person(name, institution)

                if orcid:
                    print(f"    ⚠️  Consider adding this ORCID to people.yaml: {orcid}")
                    self.discovered_orcids[name] = orcid
                else:
                    print("    ⚠️  Falling back to name search (less reliable)")

            papers = self.fetch_from_openalex(name, orcid, openalex_id, from_year)

            for paper in papers:
                if "groups" not in paper:
                    paper["groups"] = []
                paper["groups"].extend(groups)
                paper["groups"] = list(set(paper["groups"]))  # Deduplicate

            self._merge_papers(papers)

            # Be polite to APIs
            time.sleep(0.5)

        print(f"\nTotal unique publications collected: {len(self.publications)}")

    def _merge_papers(self, papers: List[Dict]):
        for paper in papers:
            doi = paper.get("doi")

            if doi and doi in self.publications:
                existing = self.publications[doi]
                existing["groups"] = list(set(existing["groups"] + paper["groups"]))

                if len(str(paper)) > len(str(existing)):
                    paper["groups"] = existing["groups"]
                    self.publications[doi] = paper
            elif doi:
                self.publications[doi] = paper
            else:
                # No DOI - use title+year as fallback key
                key = f"{paper.get("title", "")}_{paper.get("year", "")}"
                if key not in self.publications:
                    self.publications[key] = paper
                else:
                    existing = self.publications[key]
                    existing["groups"] = list(set(existing["groups"] + paper["groups"]))

    def get_required_collaborators_for_member(
        self, member: Dict, group_name: str
    ) -> List[str]:
        required = set()

        group_settings = self.group_config.get(group_name, {})
        required.update(group_settings.get("required_collaborators", []))
        required.update(member.get("required_collaborators", []))

        return list(required)

    def filter_group_collaborators(self):
        print("\nApplying group collaborator filters...")

        group_removals = {}
        removed_completely = []

        members_by_name = {member.get("name"): member for member in self.people}

        members_by_orcid = {}
        for member in self.people:
            orcid = member.get("orcid")
            if orcid:
                members_by_orcid[orcid] = member

        for name, orcid in self.discovered_orcids.items():
            member = members_by_name.get(name)
            if member:
                members_by_orcid[orcid] = member

        for group_name in self.group_config.keys():
            removed_count = 0

            for key, paper in list(self.publications.items()):
                groups = paper.get("groups", [])

                if group_name in groups:
                    authors = paper.get("authors", [])

                    required_collabs = set()
                    group_settings = self.group_config.get(group_name, {})
                    required_collabs.update(
                        group_settings.get("required_collaborators", [])
                    )

                    authorships = paper.get("raw_data", {}).get("authorships", [])

                    for authorship in authorships:
                        author_info = authorship.get("author", {})
                        author_name = author_info.get("display_name", "")
                        author_orcid = (author_info.get("orcid") or "").replace(
                            "https://orcid.org/", ""
                        )

                        member = None

                        # Priority 1: Match by ORCID (most reliable)
                        if author_orcid and author_orcid in members_by_orcid:
                            candidate = members_by_orcid[author_orcid]
                            if group_name in candidate.get("groups", []):
                                member = candidate

                        # Priority 2: Exact name match
                        if not member:
                            candidate = members_by_name.get(author_name)
                            if candidate and group_name in candidate.get("groups", []):
                                member = candidate

                        # Priority 3: Fuzzy name match (fallback)
                        if not member:
                            for member_name, member_data in members_by_name.items():
                                if group_name not in member_data.get("groups", []):
                                    continue

                                # Simple fuzzy match: check if core name parts match
                                author_parts = set(
                                    author_name.lower().replace(".", "").split()
                                )
                                member_parts = set(
                                    member_name.lower().replace(".", "").split()
                                )

                                # If member name parts are a subset of author parts
                                if member_parts.issubset(author_parts):
                                    member = member_data
                                    break

                        if member and group_name in member.get("groups", []):
                            required_collabs.update(
                                member.get("required_collaborators", [])
                            )

                    if required_collabs:
                        has_collaborator = any(
                            collab in authors for collab in required_collabs
                        )

                        if not has_collaborator:
                            paper["groups"] = [
                                group for group in groups
                                if group != group_name
                            ]
                            removed_count += 1

                            if not paper["groups"]:
                                removed_completely.append(key)
                                del self.publications[key]

            if removed_count > 0:
                group_removals[group_name] = removed_count

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
        print("\nGenerating publications.json...")

        sorted_pubs = sorted(
            self.publications.values(),
            key=lambda p: (-(p.get("year") or 0), p.get("title", ""))
        )

        output_file = os.path.join(self.output_dir, "publications.json")
        with open(output_file, "w") as file:
            json.dump(sorted_pubs, file, indent=2)

        print(f"  Wrote {len(sorted_pubs)} publications to {output_file}")

    def generate_html_outputs(self):
        print("\nGenerating HTML outputs...")

        for group_name in self.group_config.keys():
            group_pubs = [
                publication for publication in self.publications.values()
                if group_name in publication.get("groups", [])
            ]

            group_pubs.sort(key=lambda p: (-(p.get("year") or 0), p.get("title", "")))

            filename = os.path.join(
                self.output_dir,
                f"{group_name.lower()}_publications.html"
            )
            self._generate_html_file(filename, group_pubs, group_name)

    def _generate_html_file(self, filename: str,
                            publications: List[Dict], group: str):
        template_path = os.path.join("templates", "publications.html")
        with open(template_path, "r") as file:
            template = file.read()

        by_year = defaultdict(list)
        for publication in publications:
            year = publication.get("year", "Unknown")
            by_year[year].append(publication)

        publications_html = ""
        for year in sorted(by_year.keys(), reverse=True):
            publications_html += "\n    <div class=\"year-section\">\n"
            publications_html += f"        <h2 class=\"year-header\">{year}</h2>\n"

            for publication in by_year[year]:
                title = publication.get("title", "Untitled")
                authors = ", ".join(publication.get("authors", []))
                venue = publication.get("venue", "Unknown Venue")
                url = publication.get("url", "")
                doi = publication.get("doi", "")
                groups = publication.get("groups", [])

                publications_html += "        <div class=\"publication\">\n"

                if url:
                    publications_html += (
                        f"            <div class=\"title\"><a href=\"{url}\" "
                        f"target=\"_blank\">{title}</a>"
                    )
                else:
                    publications_html += f"            <div class=\"title\">{title}"

                if len(groups) > 1:
                    for badge_group in sorted(groups):
                        publications_html += (
                            f"<span class=\"group-badge\">"
                            f"{badge_group}</span>"
                        )

                publications_html += "</div>\n"

                if authors:
                    publications_html += (
                        f"            <div class=\"authors\">{authors}</div>\n"
                    )

                publications_html += f"            <div class=\"venue\">{venue}</div>\n"

                meta_parts = []
                if doi:
                    meta_parts.append(f"DOI: {doi}")
                if publication.get("citation_count"):
                    meta_parts.append(f"Citations: {publication['citation_count']}")

                if meta_parts:
                    publications_html += (
                        f"            <div class=\"meta\">{' | '.join(meta_parts)}"
                        f"</div>\n"
                    )

                publications_html += "        </div>\n"

            publications_html += "    </div>\n"

        html = template.format(
            group=group,
            last_updated=datetime.now().strftime("%B %d, %Y"),
            total_publications=len(publications),
            publications_by_year=publications_html
        )

        with open(filename, "w") as file:
            file.write(html)

        print(f"  Wrote {len(publications)} publications to {filename}")

    def run(self, from_year: Optional[int] = None):
        print("=" * 60)
        print("Publication Lists")
        print("=" * 60)

        self.load_config()
        self.fetch_all_publications(from_year)
        self.filter_group_collaborators()
        self.generate_publications_json()
        self.generate_html_outputs()

        print("\n" + "=" * 60)
        print(f"Done! Generated files in '{self.output_dir}/' directory:")
        print("  - publications.json (canonical data)")
        for group_name in self.group_config.keys():
            print(f"  - {group_name.lower()}_publications.html")
        print("=" * 60)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Fetch and aggregate academic publications for research groups"
    )
    parser.add_argument(
        "--from-year",
        type=int,
        help="Fetch only publications from this year onwards (e.g., 2020)"
    )
    args = parser.parse_args()

    if args.from_year is not None:
        current_year = datetime.now().year
        if args.from_year > current_year:
            parser.error(
                f"--from-year cannot be in the future "
                f"(current year: {current_year})"
            )
        if args.from_year < 1900:
            parser.error("--from-year must be 1900 or later")

    generator = ListGenerator("people.yaml")
    generator.run(from_year=args.from_year)


if __name__ == "__main__":
    main()
