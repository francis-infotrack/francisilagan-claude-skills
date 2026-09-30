---
type: regex
target: { source: file, path: eval-out/final-tests.txt }
pattern: '^Ran ([3-9]|\d{2,}) tests?[\s\S]*^OK'
flags: m
weight: 3
---
