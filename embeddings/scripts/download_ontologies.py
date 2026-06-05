#!/usr/bin/env python3
"""Download target ontologies for ONGA embedding comparison.

Downloads OWL and OBO files from OBO Foundry, EBI, and GitHub sources.
Uses OBO format where available (smaller files, faster parsing).

Usage:
    python download_ontologies.py              # Download primary ontologies only
    python download_ontologies.py --all        # Download primary + secondary ontologies
    python download_ontologies.py --force      # Re-download even if files exist
    python download_ontologies.py edam so      # Download specific ontologies only
"""

import argparse
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OntologySource:
    """Configuration for an ontology download."""
    name: str
    url: str
    description: str
    primary: bool = True  # Primary ontologies are core to ONGA mapping

    @property
    def filename(self) -> str:
        """Derive filename from URL extension."""
        if self.url.endswith('.owl'):
            return f'{self.name}.owl'
        elif self.url.endswith('.obo'):
            return f'{self.name}.obo'
        else:
            # Default to OBO for unknown extensions
            return f'{self.name}.obo'


# Primary ontologies - core coverage for ONGA term mapping
PRIMARY_ONTOLOGIES = [
    OntologySource(
        name='edam',
        url='http://edamontology.org/EDAM.owl',
        description='Bioinformatics operations, data types, formats (~3,500 terms)',
        primary=True,
    ),
    OntologySource(
        name='so',
        url='https://raw.githubusercontent.com/The-Sequence-Ontology/SO-Ontologies/master/Ontology_Files/so.obo',
        description='Sequence features, genomic annotations (~2,500 terms)',
        primary=True,
    ),
    OntologySource(
        name='obi',
        url='http://purl.obolibrary.org/obo/obi.owl',
        description='Biomedical investigations, assay types (~4,500 terms)',
        primary=True,
    ),
    OntologySource(
        name='go',
        url='http://purl.obolibrary.org/obo/go-basic.obo',
        description='Gene Ontology basic subset (~45,000 terms, smaller than full)',
        primary=True,
    ),
]

# Secondary ontologies - extended coverage for specialized terms
SECONDARY_ONTOLOGIES = [
    OntologySource(
        name='cl',
        url='http://purl.obolibrary.org/obo/cl.obo',
        description='Cell Ontology - cell types (~2,800 terms)',
        primary=False,
    ),
    OntologySource(
        name='uberon',
        url='http://purl.obolibrary.org/obo/uberon-basic.obo',
        description='Anatomy/tissues basic subset (~15,000 terms)',
        primary=False,
    ),
    OntologySource(
        name='efo',
        url='http://www.ebi.ac.uk/efo/efo.obo',
        description='Experimental Factor Ontology (~30,000 terms)',
        primary=False,
    ),
    OntologySource(
        name='clo',
        url='http://purl.obolibrary.org/obo/clo.owl',
        description='Cell Line Ontology - cell lines used in research (~40,000 terms)',
        primary=False,
    ),
]

ALL_ONTOLOGIES = {ont.name: ont for ont in PRIMARY_ONTOLOGIES + SECONDARY_ONTOLOGIES}


def download_file(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download a file from URL to destination.

    Args:
        url: Source URL
        dest: Destination path
        timeout: Request timeout in seconds

    Returns:
        True if download succeeded, False otherwise
    """
    try:
        print(f'  Downloading from {url}...')
        request = urllib.request.Request(
            url,
            headers={'User-Agent': 'onga-embeddings/0.1.0'}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            dest.write_bytes(content)
            size_mb = len(content) / (1024 * 1024)
            print(f'  Saved {size_mb:.1f} MB to {dest.name}')
        return True
    except urllib.error.HTTPError as e:
        print(f'  ERROR: HTTP {e.code} - {e.reason}')
        return False
    except urllib.error.URLError as e:
        print(f'  ERROR: URL error - {e.reason}')
        return False
    except TimeoutError:
        print(f'  ERROR: Download timed out after {timeout}s')
        return False
    except Exception as e:
        print(f'  ERROR: Unexpected error - {e}')
        return False


def download_ontology(
    ontology: OntologySource,
    output_dir: Path,
    force: bool = False,
) -> bool:
    """Download a single ontology.

    Args:
        ontology: Ontology configuration
        output_dir: Directory to save downloaded files
        force: If True, re-download even if file exists

    Returns:
        True if download succeeded or file already exists, False on error
    """
    dest = output_dir / ontology.filename

    if dest.exists() and not force:
        print(f'[SKIP] {ontology.name}: {dest.name} already exists')
        return True

    action = 'Re-downloading' if dest.exists() else 'Downloading'
    print(f'[{ontology.name.upper()}] {action} {ontology.description}')

    success = download_file(ontology.url, dest)
    if success:
        print(f'[{ontology.name.upper()}] Done')
    else:
        print(f'[{ontology.name.upper()}] Failed')

    return success


def download_ontologies(
    output_dir: Path,
    include_secondary: bool = False,
    force: bool = False,
    specific: list[str] | None = None,
) -> tuple[int, int]:
    """Download multiple ontologies.

    Args:
        output_dir: Directory to save downloaded files
        include_secondary: If True, also download secondary ontologies
        force: If True, re-download even if files exist
        specific: If provided, only download these ontologies by name

    Returns:
        Tuple of (success_count, failure_count)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which ontologies to download
    if specific:
        ontologies = []
        for name in specific:
            if name not in ALL_ONTOLOGIES:
                print(f'WARNING: Unknown ontology "{name}", skipping')
                print(f'  Available: {", ".join(ALL_ONTOLOGIES.keys())}')
                continue
            ontologies.append(ALL_ONTOLOGIES[name])
    else:
        ontologies = list(PRIMARY_ONTOLOGIES)
        if include_secondary:
            ontologies.extend(SECONDARY_ONTOLOGIES)

    if not ontologies:
        print('No ontologies to download')
        return 0, 0

    print(f'Downloading {len(ontologies)} ontologies to {output_dir}')
    print()

    success_count = 0
    failure_count = 0

    for ontology in ontologies:
        if download_ontology(ontology, output_dir, force=force):
            success_count += 1
        else:
            failure_count += 1
        print()

    return success_count, failure_count


def main():
    parser = argparse.ArgumentParser(
        description='Download ontologies for ONGA embedding comparison',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s                     Download primary ontologies (EDAM, SO, OBI, GO)
    %(prog)s --all               Download primary + secondary ontologies
    %(prog)s --force             Re-download all ontologies
    %(prog)s edam so             Download only EDAM and SO
    %(prog)s --list              List available ontologies
        '''
    )
    parser.add_argument(
        'ontologies',
        nargs='*',
        help='Specific ontologies to download (default: all primary)',
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Include secondary ontologies (CL, UBERON, EFO, CLO)',
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Re-download even if files already exist',
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path(__file__).parent.parent / 'data' / 'ontologies',
        help='Output directory (default: data/ontologies)',
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available ontologies and exit',
    )

    args = parser.parse_args()

    if args.list:
        print('Primary ontologies (downloaded by default):')
        for ont in PRIMARY_ONTOLOGIES:
            print(f'  {ont.name:8} - {ont.description}')
        print()
        print('Secondary ontologies (use --all to include):')
        for ont in SECONDARY_ONTOLOGIES:
            print(f'  {ont.name:8} - {ont.description}')
        return 0

    specific = args.ontologies if args.ontologies else None
    success, failures = download_ontologies(
        output_dir=args.output,
        include_secondary=args.all,
        force=args.force,
        specific=specific,
    )

    print('=' * 60)
    print(f'Summary: {success} succeeded, {failures} failed')

    if failures > 0:
        print()
        print('Some downloads failed. Try running with --force to retry.')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
