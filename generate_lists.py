import argparse
import os
import yaml
import requests
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import time


class ListGenerator:

    CONFERENCE_KEYWORDS = [
        "conference",
        "convention",
        "congress",
        "assembly",
        "colloquium",
        "seminar",
        "workshop",
        "forum",
        "roundtable",
        "summit",
        "retreat",
        "conclave",
        "symposium",
        "neural information processing systems",
    ]

    def __init__(
        self,
        people_file: str = "people.yaml",
        output_dir: str = "output",
        polite_pool_email: Optional[str] = None,
        groups: Optional[List[str]] = None,
        from_year: Optional[int] = None,
        exclusion_file: str = "excluded_dois.yaml",
        manual_file: str = "manual_publications.yaml",
        render_only: bool = False,
        data_file: Optional[str] = None,
        output_format: str = "html",
    ):
        self.people_file = people_file
        self.output_dir = output_dir
        self.exclusion_file = exclusion_file
        self.manual_file = manual_file
        self.people = []
        self.group_config = {}
        self.publications = {}
        self.discovered_orcids = {}
        self.selected_groups = groups
        self.from_year = from_year
        self.excluded_dois = set()
        self.manual_publications = []
        self.render_only = render_only
        self.output_format = output_format
        self.data_file = data_file or os.path.join(output_dir, "publications_data.yaml")

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

        self._load_excluded_dois()
        self._load_manual_publications()

        if self.selected_groups:
            invalid_groups = [
                group
                for group in self.selected_groups
                if group not in self.group_config
            ]
            if invalid_groups:
                raise ValueError(
                    "Unknown group(s): "
                    f"{', '.join(sorted(invalid_groups))}. "
                    "Available groups: "
                    f"{', '.join(sorted(self.group_config.keys()))}"
                )

            self.group_config = {
                group: self.group_config[group] for group in self.selected_groups
            }
            self.people = [
                person
                for person in self.people
                if any(
                    group in self.selected_groups for group in person.get("groups", [])
                )
            ]

        print(f"  Loaded {len(self.people)} group members")
        print(f"  Loaded configuration for {len(self.group_config)} groups")
        if self.polite_pool_email:
            print(f"  Using polite pool email: {self.polite_pool_email}")

    def fetch_all_publications(self):
        print("\nFetching publications...")
        if self.from_year:
            print(f"  Filtering to publications from {self.from_year} onwards")

        for person in self.people:
            name = person.get("name")
            orcid = person.get("orcid")
            institution = person.get("institution")
            groups = person.get("groups", [])

            print(f"\n  Processing: {name} ({', '.join(groups)})")

            # Try to find ORCID if not provided
            if not orcid:
                print("    No ORCID provided, attempting lookup...")
                orcid = self._find_orcid_for_person(name, institution)

                if orcid:
                    print(f"    ⚠️  Consider adding this ORCID to people.yaml: {orcid}")
                    self.discovered_orcids[name] = orcid
                else:
                    print("    ⚠️  Falling back to name search (less reliable)")

            papers = self._fetch_from_openalex(name, orcid, self.from_year)

            for paper in papers:
                paper["groups"].extend(groups)
                paper["groups"] = list(set(paper["groups"]))  # Deduplicate

            self._merge_papers(papers)

            # Be polite to APIs
            time.sleep(0.5)

        print(f"\nTotal unique publications collected: {len(self.publications)}")

    def add_manual_publications(self):
        if not self.manual_publications:
            return

        print("\nAdding manual publications...")
        added_count = 0

        for publication in self.manual_publications:
            publication_year = publication.get("year")
            if (
                self.from_year
                and publication_year
                and publication_year < self.from_year
            ):
                continue

            publication_groups = publication.get("groups", [])
            if self.selected_groups:
                publication_groups = [
                    group
                    for group in publication_groups
                    if group in self.selected_groups
                ]
                if not publication_groups:
                    continue

            work_type = publication.get("type", "article")
            publication_date = publication.get("publication_date")
            if not publication_date and publication_year:
                publication_date = f"{publication_year}-01-01"
            elif not publication_date:
                publication_date = "0000-00-00"

            paper = self._create_paper(
                doi=publication.get("doi"),
                title=publication.get("title", ""),
                year=publication_year,
                publication_date=publication_date,
                authors=publication.get("authors", []),
                venue=publication.get("venue"),
                url=publication.get("url") or publication.get("doi"),
                citation_count=publication.get("citation_count", 0),
                work_type=work_type,
                venue_type=publication.get("venue_type"),
                display_type=publication.get("display_type", "articles"),
                source="manual",
                raw_data={"type": work_type},
                groups=publication_groups,
            )

            self._merge_papers([paper])
            added_count += 1

        if added_count > 0:
            print(f"  Added {added_count} manual publications")

    def filter_group_collaborators(self):
        print("\nApplying group collaborator filters...")
        print("  (Manual publications are exempt from this filter)")

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
                    if paper.get("source") == "manual":
                        continue

                    authors = paper.get("authors", [])

                    required_collabs = set()
                    group_settings = self.group_config.get(group_name, {})
                    required_collabs.update(
                        group_settings.get("required_collaborators", [])
                    )

                    authorships = paper.get("raw_data", {}).get("authorships", [])

                    for authorship in authorships:
                        member = self._find_member_for_authorship(
                            authorship, group_name, members_by_orcid, members_by_name
                        )
                        if member:
                            required_collabs.update(
                                member.get("required_collaborators", [])
                            )

                    if required_collabs:
                        has_collaborator = any(
                            collab in authors for collab in required_collabs
                        )

                        if not has_collaborator:
                            paper["groups"] = [
                                group for group in groups if group != group_name
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

    def save_data(self):
        print(f"\nSaving publication data to {self.data_file}...")

        canonical_publications = []
        for paper in self.publications.values():
            clean_paper = {
                field: value for field, value in paper.items() if field != "raw_data"
            }
            canonical_publications.append(clean_paper)

        data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "from_year": self.from_year,
                "groups": list(self.group_config.keys()),
                "total_publications": len(canonical_publications),
            },
            "publications": canonical_publications,
        }

        with open(self.data_file, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        print(f"  Saved {len(canonical_publications)} publications")

    def load_data(self):
        print(f"\nLoading publication data from {self.data_file}...")

        if not os.path.exists(self.data_file):
            raise FileNotFoundError(
                f"Data file not found: {self.data_file}. "
                f"Run without --render-only first to fetch publications."
            )

        with open(self.data_file, "r") as f:
            data = yaml.safe_load(f)

        metadata = data.get("metadata", {})
        print(f"  Data generated at: {metadata.get('generated_at', 'unknown')}")
        print(f"  Groups in data: {', '.join(metadata.get('groups', []))}")

        for paper in data.get("publications", []):
            paper["raw_data"] = {}
            self.publications[self._get_paper_key(paper)] = paper

            for group in paper.get("groups", []):
                if group not in self.group_config:
                    self.group_config[group] = {}

        if self.selected_groups:
            self.group_config = {
                group: self.group_config[group]
                for group in self.selected_groups
                if group in self.group_config
            }
            self.publications = {
                publication_key: publication
                for publication_key, publication in self.publications.items()
                if any(
                    group in self.selected_groups
                    for group in publication.get("groups", [])
                )
            }

        print(f"  Loaded {len(self.publications)} publications")

    def generate_html_outputs(self):
        print("\nGenerating HTML outputs...")

        env = Environment(loader=FileSystemLoader("templates"))

        for group_name in self.group_config.keys():
            group_publications = [
                publication
                for publication in self.publications.values()
                if group_name in publication.get("groups", [])
            ]

            group_template_name = f"{group_name.lower()}_publications.html"
            default_template_name = "publications.html"

            template_path = os.path.join("templates", group_template_name)
            if os.path.exists(template_path):
                template = env.get_template(group_template_name)
                print(f"  Using group template: {group_template_name}")
            else:
                template = env.get_template(default_template_name)

            filename = os.path.join(
                self.output_dir, f"{group_name.lower()}_publications.html"
            )
            self._generate_html_file(filename, group_publications, group_name, template)

    def run(self):
        print("=" * 60)
        print("Publication Lists")
        print("=" * 60)
        groups_str = ', '.join(self.selected_groups) if self.selected_groups else 'all'
        print(f"  Groups:      {groups_str}")
        print(f"  Format:      {self.output_format}")
        from_year_str = self.from_year if self.from_year is not None else 'all'
        print(f"  From year:   {from_year_str}")
        print(f"  Render only: {self.render_only}")
        print("=" * 60)

        if self.render_only:
            self.load_data()
        else:
            self.load_config()
            self.fetch_all_publications()
            self.add_manual_publications()
            self.filter_group_collaborators()
            self.save_data()

        if self.output_format == "yaml":
            self.generate_yaml_outputs()
        else:
            self.generate_html_outputs()

        ext = self.output_format
        print("\n" + "=" * 60)
        print(f"Done! Generated files in '{self.output_dir}/' directory:")
        for group_name in self.group_config.keys():
            print(f"  - {group_name.lower()}_publications.{ext}")
        print("=" * 60)

    def generate_yaml_outputs(self):
        print("\nGenerating YAML outputs...")

        env = Environment(loader=FileSystemLoader("templates"))
        env.filters["toyaml"] = lambda value: yaml.dump(
            value, default_flow_style=True, allow_unicode=True, width=float("inf")
        ).split("\n")[0]

        for group_name in self.group_config.keys():
            group_publications = [
                publication
                for publication in self.publications.values()
                if group_name in publication.get("groups", [])
            ]

            group_template_name = f"{group_name.lower()}_publications.yaml"
            default_template_name = "publications.yaml"

            template_path = os.path.join("templates", group_template_name)
            if os.path.exists(template_path):
                template = env.get_template(group_template_name)
                print(f"  Using group template: {group_template_name}")
            else:
                template = env.get_template(default_template_name)

            filename = os.path.join(
                self.output_dir, f"{group_name.lower()}_publications.yaml"
            )
            self._generate_yaml_file(filename, group_publications, group_name, template)

    def _generate_yaml_file(
        self, filename: str, publications: List[Dict], group: str, template
    ):
        sorted_publications = sorted(publications, key=self._get_date_sort_key)

        content = template.render(
            publications=sorted_publications,
        )

        with open(filename, "w") as file:
            file.write(content)

        print(f"  Wrote {len(publications)} publications to {filename}")

    def _fetch_from_openalex(
        self,
        author_name: str,
        orcid: Optional[str] = None,
        from_year: Optional[int] = None,
    ) -> List[Dict]:
        papers = []

        try:
            if orcid:
                # ORCID is most reliable
                url = (
                    f"https://api.openalex.org/works?filter="
                    f"authorships.author.orcid:{orcid}"
                )
                strategy = f"ORCID: {orcid}"
            else:
                # Fall back to name search (less reliable)
                url = (
                    f"https://api.openalex.org/works?filter="
                    f"raw_author_name.search:{author_name}"
                )
                strategy = "name search (fallback)"

            if from_year:
                url += f",from_publication_date:{from_year}-01-01"

            base_url = url + "&per-page=200"
            if self.polite_pool_email:
                base_url += f"&mailto={self.polite_pool_email}"

            print(f"    Querying OpenAlex for {author_name} using {strategy}...")

            page = 1
            while True:
                page_url = base_url + f"&page={page}"
                response = requests.get(page_url, timeout=30)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    break

                for work in results:
                    paper = self._parse_openalex_work(work)
                    if paper:
                        papers.append(paper)

                if len(results) < 200:
                    break

                page += 1

            print(f"    Found {len(papers)} papers from OpenAlex")

        except Exception as e:
            print(f"    Warning: OpenAlex fetch failed for {author_name}: {e}")

        return papers

    def _find_orcid_for_person(
        self, author_name: str, institution_name: Optional[str] = None
    ) -> Optional[str]:
        try:
            print(f"    Attempting to find ORCID for {author_name}...")

            name_parts = author_name.strip().split()
            if len(name_parts) < 2:
                print("    Cannot parse name into first/last name")
                return None

            given_name = name_parts[0]
            family_name = " ".join(name_parts[1:])

            query_parts = [f"given-names:{given_name}", f"family-name:{family_name}"]

            if institution_name:
                query_parts.append(f'affiliation-org-name:"{institution_name}"')

            query = "+AND+".join(query_parts)
            url = f"https://pub.orcid.org/v3.0/search/?q={query}&rows=5"

            headers = {"Accept": "application/json"}

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = data.get("result", [])

            if not results:
                print(f"    No ORCID found for {author_name}")
                return None

            if len(results) > 1:
                print(f"    Found {len(results)} possible matches:")
                for rank, result in enumerate(results[:3], 1):
                    orcid = self._extract_orcid_from_result(result)
                    print(f"      {rank}. ORCID: {orcid}")
                print("    Using first match (most relevant)")

            orcid = self._extract_orcid_from_result(results[0])
            if orcid:
                print(f"    Found ORCID: {orcid}")
                return orcid

        except Exception as e:
            print(f"    Warning: ORCID lookup failed: {e}")

        return None

    def _create_paper(
        self,
        doi: Optional[str],
        title: str,
        year: Optional[int],
        publication_date: Optional[str],
        authors: List[str],
        venue: Optional[str],
        url: Optional[str],
        citation_count: int,
        work_type: str,
        venue_type: Optional[str],
        display_type: str,
        source: str,
        raw_data: Dict,
        groups: Optional[List[str]] = None,
    ) -> Dict:
        return {
            "doi": doi,
            "title": title,
            "year": year,
            "publication_date": publication_date,
            "authors": authors,
            "venue": venue,
            "url": url,
            "citation_count": citation_count,
            "type": work_type,
            "venue_type": venue_type,
            "display_type": display_type,
            "source": source,
            "raw_data": raw_data,
            "groups": groups if groups is not None else [],
        }

    def _parse_openalex_work(self, work: Dict) -> Optional[Dict]:
        try:
            doi = (work.get("doi") or "").replace("https://doi.org/", "")

            if doi and doi.lower() in self.excluded_dois:
                return None

            work_type = work.get("type", "")
            venue = self._extract_venue(work)
            venue_type = None
            primary_location = work.get("primary_location")
            if primary_location:
                source = primary_location.get("source")
                if source:
                    venue_type = source.get("type")

            display_type = self._get_display_type(work_type, venue_type, venue)
            authors = [
                author.get("author", {}).get("display_name", "")
                for author in work.get("authorships", [])
            ]

            paper = self._create_paper(
                doi=doi or None,
                title=work.get("title", ""),
                year=work.get("publication_year"),
                publication_date=work.get("publication_date"),
                authors=authors,
                venue=venue,
                url=work.get("doi") or work.get("id", ""),
                citation_count=work.get("cited_by_count", 0),
                work_type=work_type,
                venue_type=venue_type,
                display_type=display_type,
                source="openalex",
                raw_data=work,
            )

            return paper if paper["title"] else None

        except Exception as e:
            print(f"    Warning: Failed to parse OpenAlex work: {e}")
            return None

    def _extract_orcid_from_result(result: Dict) -> str:
        uri = result.get("orcid-identifier", {}).get("uri", "")
        return uri.replace("https://orcid.org/", "")

    def _extract_venue(self, work: Dict) -> Optional[str]:
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        return source.get("display_name") or location.get("raw_source_name")

    def _get_display_type(
        self, work_type: str, venue_type: Optional[str], venue: Optional[str]
    ) -> str:
        venue_lower = (venue or "").lower()
        is_conference_venue = any(
            keyword in venue_lower for keyword in self.CONFERENCE_KEYWORDS
        )

        if venue_type == "journal" and work_type == "article":
            return "journals"
        elif venue_type == "conference" and work_type == "article":
            return "conferences"
        elif is_conference_venue and work_type == "article":
            return "conferences"
        elif work_type == "preprint":
            return "preprints"
        elif work_type == "book-chapter":
            return "books"
        elif work_type == "article":
            return "articles"
        else:
            return "others"

    def _should_prefer_over(self, paper: Dict, existing: Dict) -> bool:
        paper_venue = (paper.get("venue") or "").lower()
        existing_venue = (existing.get("venue") or "").lower()

        paper_is_arxiv = "arxiv" in paper_venue or "cornell university" in paper_venue
        existing_is_arxiv = (
            "arxiv" in existing_venue or "cornell university" in existing_venue
        )

        paper_type = paper.get("type", "")
        existing_type = existing.get("type", "")
        paper_is_preprint = paper_type == "preprint"
        existing_is_preprint = existing_type == "preprint"

        # Prefer non-preprint over preprint
        if not paper_is_preprint and existing_is_preprint:
            return True
        if paper_is_preprint and not existing_is_preprint:
            return False

        # Prefer non-arXiv over arXiv
        if not paper_is_arxiv and existing_is_arxiv:
            return True
        if paper_is_arxiv and not existing_is_arxiv:
            return False

        # If both are arXiv or both are not, prefer more complete info
        return len(str(paper)) > len(str(existing))

    def _get_paper_key(self, paper: Dict) -> str:
        doi = paper.get("doi")
        if doi:
            return doi
        return (
            f"{self._normalize_title(paper.get('title', ''))}_"
            f"{paper.get('year', '')}"
        )

    def _find_member_for_authorship(
        self,
        authorship: Dict,
        group_name: str,
        members_by_orcid: Dict,
        members_by_name: Dict,
    ) -> Optional[Dict]:
        author_info = authorship.get("author", {})
        author_name = author_info.get("display_name", "")
        author_orcid = (author_info.get("orcid") or "").replace(
            "https://orcid.org/", ""
        )

        # Priority 1: Match by ORCID (most reliable)
        if author_orcid and author_orcid in members_by_orcid:
            candidate = members_by_orcid[author_orcid]
            if group_name in candidate.get("groups", []):
                return candidate

        # Priority 2: Exact name match
        candidate = members_by_name.get(author_name)
        if candidate and group_name in candidate.get("groups", []):
            return candidate

        # Priority 3: Fuzzy name match (fallback)
        for member_name, member_data in members_by_name.items():
            if group_name not in member_data.get("groups", []):
                continue
            author_parts = set(author_name.lower().replace(".", "").split())
            member_parts = set(member_name.lower().replace(".", "").split())
            if member_parts.issubset(author_parts):
                return member_data

        return None

    def _normalize_title(self, title: str) -> str:
        if not title:
            return ""
        normalized = " ".join(title.lower().split())
        return normalized

    def _load_yaml_list(self, filepath: str, key: str) -> list:
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r") as file:
                data = yaml.safe_load(file)
                if data and key in data:
                    items = data[key]
                    print(f"  Loaded {len(items)} {key} from {filepath}")
                    return items
        except Exception as e:
            print(f"  Warning: Could not load {filepath}: {e}")
        return []

    def _load_excluded_dois(self):
        dois = self._load_yaml_list(self.exclusion_file, "excluded_dois")
        self.excluded_dois = set(doi.lower() for doi in dois)

    def _load_manual_publications(self):
        self.manual_publications = self._load_yaml_list(
            self.manual_file, "manual_publications"
        )

    def _build_title_index(self) -> Dict[str, str]:
        index = {}
        for key, paper in self.publications.items():
            norm = self._normalize_title(paper.get("title", ""))
            if norm:
                index[norm] = key
        return index

    def _merge_papers(self, papers: List[Dict]):
        title_index = self._build_title_index()

        for paper in papers:
            doi = paper.get("doi")
            merged = False

            # First, try to merge by DOI
            if doi and doi in self.publications:
                existing = self.publications[doi]
                existing["groups"] = list(set(existing["groups"] + paper["groups"]))

                if self._should_prefer_over(paper, existing):
                    paper["groups"] = existing["groups"]
                    self.publications[doi] = paper
                merged = True

            # If not merged by DOI, try to find duplicate by title
            if not merged:
                paper_title = self._normalize_title(paper.get("title", ""))
                paper_year = paper.get("year")
                existing_key = title_index.get(paper_title) if paper_title else None

                if existing_key and existing_key in self.publications:
                    existing = self.publications[existing_key]
                    existing_year = existing.get("year")

                    years_match = (
                        not paper_year
                        or not existing_year
                        or paper_year == existing_year
                        or abs(paper_year - existing_year) <= 1
                    )

                    if years_match:
                        existing["groups"] = list(
                            set(existing["groups"] + paper["groups"])
                        )

                        if self._should_prefer_over(paper, existing):
                            paper["groups"] = existing["groups"]
                            del self.publications[existing_key]
                            new_key = self._get_paper_key(paper)
                            self.publications[new_key] = paper
                            title_index[paper_title] = new_key

                        merged = True

            # If still not merged, add as new paper
            if not merged:
                new_key = self._get_paper_key(paper)
                self.publications[new_key] = paper
                norm = self._normalize_title(paper.get("title", ""))
                if norm:
                    title_index[norm] = new_key

    def _generate_html_file(
        self, filename: str, publications: List[Dict], group: str, template
    ):
        by_year = defaultdict(list)
        for publication in publications:
            year = publication.get("year", "Unknown")
            by_year[year].append(publication)

        for year in by_year:
            by_year[year].sort(key=self._get_date_sort_key)

        html = template.render(
            group=group,
            last_updated=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            total_publications=len(publications),
            years=sorted(by_year.keys(), reverse=True),
            by_year=by_year,
        )

        with open(filename, "w") as file:
            file.write(html)

        print(f"  Wrote {len(publications)} publications to {filename}")

    def _get_date_sort_key(self, publication: Dict):
        date_str = publication.get("publication_date") or "0000-00-00"
        return -int(date_str.replace("-", ""))


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Fetch and aggregate academic publications for research groups"
    )
    parser.add_argument(
        "--from-year",
        type=int,
        help="Fetch only publications from this year onwards (e.g., 2020)",
    )
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        help=(
            "Run only for a specific group. "
            "Repeat for multiple groups (e.g., --group VIOS --group CHAI)."
        ),
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help=(
            "Skip fetching; re-render HTML from the existing data file. "
            "Useful for iterating on templates."
        ),
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help="Path to the intermediate data file (default: publications_data.yaml)",
    )
    parser.add_argument(
        "--format",
        choices=["html", "yaml"],
        default="html",
        help="Output format: html (default) or yaml",
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

    if args.render_only and args.from_year is not None:
        parser.error("--from-year has no effect with --render-only")

    try:
        generator = ListGenerator(
            groups=args.groups,
            from_year=args.from_year,
            render_only=args.render_only,
            data_file=args.data_file,
            output_format=args.format,
        )
        generator.run()
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
