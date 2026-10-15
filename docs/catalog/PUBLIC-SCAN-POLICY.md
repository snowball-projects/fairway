# Public text scan policy

The exporter, Pages builder and browser apply the same explicit character rules
before accepting public text. This check rejects retained evidence and local path
tokens. Full DTO validation still checks typed columns, scope and source bindings.
Validation never changes the emitted text, stored observation or displayed claim.

Only a temporary validation copy maps these 30 characters to ASCII space:
U+0009 through U+000D, U+001C through U+0020, U+0085, U+00A0, U+1680,
U+2000 through U+200A, U+2028, U+2029, U+202F, U+205F, U+3000 and U+FEFF.
Only ASCII A through Z are folded to lowercase. No language engine's Unicode
whitespace class, digit class, case folding or word boundary decides acceptance.

The bounded `/ea` financial exception applies only to `conditions` in an explicit
`per_person` row with id, observation_id, fee_kind, amount_kind and amount_min.
It accepts a leading currency amount or printed notation with a documented rider
count per cart. Keywords and digits in this exception are ASCII. Termination is
explicit space, end or listed punctuation. Unsupported non-ASCII financial syntax
fails closed where it would otherwise resemble a path; it is never transliterated.
No exception applies to other fields or a second private path later in the claim.

Public HTTP(S) links are excluded from the path scan only at the start or after
an explicit ASCII nonword delimiter (U+0000..002F, 003A..0040, 005B..005E,
0060, 007B..007F) or the listed quotes “ ” ‘ ’ « ».
HTTP(S) tokens end at whitespace, ASCII quotes/backtick, angle brackets or any
of those six smart quotes. A closing quote cannot swallow a following POSIX,
drive or UNC path. Shared36-case URL controls and synchronized complete DTO
qualification tests cover those terminations without rewriting the source text.
Other Unicode prefixes are conservative: they do not grant a URL exemption.
Absolute POSIX path tokens at start or after the listed punctuation/space,
file URIs, drive-colon slash/backslash tokens and two or more consecutive
backslashes are rejected. Drive letters include ASCII and the four Unicode
casefold confusables İ, ı, ſ and K. Ordinary slash compounds remain unchanged.

The original independent 33-case finding is preserved byte-exact in
`per-each-unicode-original.json` (SHA-256
`f5544a6e7bc0121fa473cf244bb4297a3285d38c9255df4a52b095184dbfa9a9`).
Its recorded historical decisions describe the rejected predecessor, not this
policy. The separate 200-case normative fixture covers those exact strings,
all 30 delimiters, unsupported case/digits, links, drive and UNC paths.
Shared tests exercise all three validators and verify nonmutation. Complete
transport tests exercise normal builds and two credential-free browser GETs,
including U+0085 and U+FEFF acceptance and private-path rejection.

This correction changes the public exporter copy beyond writer source 4df3e0f.
The writer repository is untouched. Reviewed release768 JSON, gzip and manifest
remain byte-identical. Later quantity or historical-heading exceptions are
outside this release and need their own reviewed composition.
