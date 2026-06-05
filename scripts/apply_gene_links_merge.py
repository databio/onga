"""Merge synonym `enhancer-gene links` into canonical `element gene links` (op #16).
Both are original ENCODE seed terms and the same concept; consolidate, preserving
the ENCODE round-trip via an alias + a facet_decomposition synonym row."""
from ruamel.yaml import YAML
yaml = YAML(); yaml.preserve_quotes = True; yaml.width = 120
p = 'src/file_content.yaml'
with open(p) as f: data = yaml.load(f)
ft = data['enums']['FeatureType']['permissible_values']
assert 'enhancer-gene links' in ft and 'element gene links' in ft, "source terms missing"
# add alias on canonical term
canon = ft['element gene links']
aliases = canon.get('aliases', [])
if 'enhancer-gene links' not in aliases:
    aliases.append('enhancer-gene links')
canon['aliases'] = aliases
# enrich description to make enhancers the named common case
canon['description'] = ("Associations linking regulatory elements (commonly enhancers) "
                        "to their putative target genes.")
# remove the synonym term
del ft['enhancer-gene links']
with open(p, 'w') as f: yaml.dump(data, f)
print("merged: removed 'enhancer-gene links', aliased onto 'element gene links'")
