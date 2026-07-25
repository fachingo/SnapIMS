# Local Matching Rules

## Search order

1. Exact normalized canonical title.
2. Exact normalized alias.
3. Exact title plus release year.
4. Previous approved recognition-to-Movie mappings and aliases.
5. Bounded FTS title/alias candidates.
6. Conservative fuzzy/variant expansion only after exact search fails.

## Normalization

The normalizer handles Unicode form, case, whitespace, apostrophes, dashes, punctuation, leading articles, common subtitle separators and conservative Roman/numeric sequel variants. It does not erase release year or collapse unrelated works.

Examples that remain separable:

- *The Thing* (1951) and *The Thing* (1982)
- *The Fly* (1958) and *The Fly* (1986)
- *Crash* (1978) and *Crash* (1996)
- *It* (1990 television miniseries) and *It* (2017 film)
- *Halloween* (1978) and *Halloween* (2007)

## Automatic-selection rule

A result may be selected automatically only when it is materially unique. Safe evidence includes one exact local title/alias with no conflicting year, or exact title plus agreeing year and film classification. Unsafe cases remain ambiguous when multiple Movies share the title, year conflicts, film and television results are credible, or ranking separation is insufficient.

Thresholds are catalog settings. Stored scores rank evidence; they are not presented as fabricated statistical certainty. Every automatic decision stores the method and reason.

## Title precedence in Review

1. Operator-saved title.
2. Unique linked local Movie canonical title.
3. Unique newly ingested Movie canonical title.
4. Original AI suggestion.
5. Manual untitled state.

Recognition history is never overwritten and disagreements remain visible.
